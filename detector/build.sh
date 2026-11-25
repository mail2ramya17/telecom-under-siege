#!/usr/bin/env bash
# Compile and run the CDR exfiltration detector against the synthetic sample log.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build
mapfile -t SOURCES < <(find src/main/java -name '*.java')
javac -Xlint:all -Werror -d build "${SOURCES[@]}"
java -cp build io.hhit.telecom.CdrExfilDetector "${1:-sample/warehouse_query_log.csv}"
