package io.hhit.telecom;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.ArrayDeque;
import java.util.Comparator;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * Detects bulk exfiltration of call detail records (CDRs) and subscriber data
 * from a cloud data warehouse, using its query-audit log.
 *
 * <p>This is the "Cloud data theft" path from the video: stolen credentials,
 * a login without MFA, then bulk queries against sensitive tables.
 *
 * <p>Input CSV columns: timestamp,user,source_ip,auth_method,table,rows_returned
 *
 * <p>Rules:
 * <ul>
 *   <li>NO_MFA_SENSITIVE  - password-only login touching a sensitive table</li>
 *   <li>NEW_SOURCE_IP     - user queries from an IP never seen in their baseline</li>
 *   <li>BULK_VOLUME       - rows returned far above the user's own baseline</li>
 *   <li>QUERY_BURST       - many sensitive queries in a short window</li>
 * </ul>
 * Exit code 2 when any HIGH finding is raised, so it can gate a pipeline or alert.
 */
public final class CdrExfilDetector {

    record Event(Instant ts, String user, String ip, String auth, String table, long rows) {}

    record Finding(String severity, String rule, Event event, String detail) {}

    static final Set<String> SENSITIVE_PREFIXES = Set.of("cdr_", "subscriber_", "sms_", "location_", "billing_");
    static final double BASELINE_FRACTION = 0.5;   // first half of each user's history = baseline
    static final long BULK_MIN_ROWS = 100_000;
    static final double BULK_MULTIPLIER = 20.0;
    static final int BURST_COUNT = 5;
    static final Duration BURST_WINDOW = Duration.ofMinutes(10);

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("usage: java io.hhit.telecom.CdrExfilDetector <query_log.csv>");
            System.exit(64);
        }
        List<Event> events = parse(Path.of(args[0]));
        List<Finding> findings = analyze(events);
        report(events, findings);
        boolean high = findings.stream().anyMatch(f -> f.severity().equals("HIGH"));
        System.exit(high ? 2 : 0);
    }

    static List<Event> parse(Path csv) throws IOException {
        List<Event> out = new ArrayList<>();
        List<String> lines = Files.readAllLines(csv);
        for (int i = 0; i < lines.size(); i++) {
            String line = lines.get(i).strip();
            if (line.isEmpty() || line.startsWith("#") || line.startsWith("timestamp,")) continue;
            String[] f = line.split(",");
            if (f.length != 6) {
                System.err.printf("line %d: expected 6 columns, got %d - skipped%n", i + 1, f.length);
                continue;
            }
            out.add(new Event(Instant.parse(f[0]), f[1], f[2], f[3].toLowerCase(Locale.ROOT),
                    f[4].toLowerCase(Locale.ROOT), Long.parseLong(f[5])));
        }
        out.sort(Comparator.comparing(Event::ts));
        return out;
    }

    static boolean sensitive(String table) {
        return SENSITIVE_PREFIXES.stream().anyMatch(table::startsWith);
    }

    static List<Finding> analyze(List<Event> events) {
        Map<String, List<Event>> byUser = new HashMap<>();
        for (Event e : events) byUser.computeIfAbsent(e.user(), k -> new ArrayList<>()).add(e);

        List<Finding> findings = new ArrayList<>();
        for (Map.Entry<String, List<Event>> entry : byUser.entrySet()) {
            List<Event> history = entry.getValue();
            int baseN = Math.max(1, (int) Math.floor(history.size() * BASELINE_FRACTION));
            List<Event> baseline = history.subList(0, baseN);

            Set<String> knownIps = new HashSet<>();
            for (Event e : baseline) knownIps.add(e.ip());
            long medianRows = median(baseline.stream().mapToLong(Event::rows).toArray());

            Deque<Event> window = new ArrayDeque<>();
            Set<String> burstReported = new HashSet<>();
            for (int i = 0; i < history.size(); i++) {
                Event e = history.get(i);
                boolean sens = sensitive(e.table());

                if (sens && e.auth().equals("password")) {
                    findings.add(new Finding("HIGH", "NO_MFA_SENSITIVE", e,
                            "password-only session queried " + e.table()));
                }
                if (i >= baseN && !knownIps.contains(e.ip())) {
                    findings.add(new Finding(sens ? "HIGH" : "MEDIUM", "NEW_SOURCE_IP", e,
                            "first query from " + e.ip() + " (baseline IPs: " + knownIps.size() + ")"));
                    knownIps.add(e.ip());
                }
                if (i >= baseN && e.rows() >= BULK_MIN_ROWS
                        && e.rows() >= BULK_MULTIPLIER * Math.max(1, medianRows)) {
                    findings.add(new Finding(sens ? "HIGH" : "MEDIUM", "BULK_VOLUME", e,
                            String.format("%,d rows vs baseline median %,d (%.0fx)",
                                    e.rows(), medianRows, e.rows() / (double) Math.max(1, medianRows))));
                }
                if (sens) {
                    window.addLast(e);
                    while (!window.isEmpty()
                            && Duration.between(window.peekFirst().ts(), e.ts()).compareTo(BURST_WINDOW) > 0) {
                        window.removeFirst();
                    }
                    String key = e.user() + "@" + window.peekFirst().ts();
                    if (window.size() >= BURST_COUNT && burstReported.add(key)) {
                        findings.add(new Finding("MEDIUM", "QUERY_BURST", e,
                                window.size() + " sensitive queries within " + BURST_WINDOW.toMinutes() + " min"));
                    }
                }
            }
        }
        findings.sort(Comparator.comparing((Finding f) -> f.severity().equals("HIGH") ? 0 : 1)
                .thenComparing(f -> f.event().ts()));
        return findings;
    }

    static long median(long[] values) {
        if (values.length == 0) return 0;
        long[] v = values.clone();
        java.util.Arrays.sort(v);
        int m = v.length / 2;
        return v.length % 2 == 1 ? v[m] : (v[m - 1] + v[m]) / 2;
    }

    static void report(List<Event> events, List<Finding> findings) {
        System.out.printf("CDR exfiltration detector - %d events, %d findings%n%n", events.size(), findings.size());
        if (findings.isEmpty()) {
            System.out.println("No suspicious activity found.");
            return;
        }
        System.out.printf("%-7s %-17s %-21s %-12s %s%n", "SEV", "RULE", "TIME (UTC)", "USER", "DETAIL");
        for (Finding f : findings) {
            System.out.printf("%-7s %-17s %-21s %-12s %s%n", f.severity(), f.rule(),
                    f.event().ts().toString().replace("T", " ").replace("Z", ""), f.event().user(), f.detail());
        }
        Map<String, Long> rowsByUser = new HashMap<>();
        for (Finding f : findings) {
            if (f.rule().equals("BULK_VOLUME")) rowsByUser.merge(f.event().user(), f.event().rows(), Long::sum);
        }
        rowsByUser.forEach((u, r) -> System.out.printf("%nPotentially exfiltrated by %s: %,d rows%n", u, r));
    }
}
