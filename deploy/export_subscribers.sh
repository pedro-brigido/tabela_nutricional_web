#!/bin/bash
# Exporta emails cadastrados do SQLite para CSV
OUTPUT="${1:-subscribers_$(date +%Y%m%d_%H%M%S).csv}"

docker exec tabela_nutricional_web python -c "
import sqlite3, csv, sys
conn = sqlite3.connect('/app/data/subscribers.db')
rows = conn.execute('SELECT id, email, subscribed_at, ip FROM subscribers ORDER BY id').fetchall()
w = csv.writer(sys.stdout)
w.writerow(['id', 'email', 'subscribed_at', 'ip'])
w.writerows(rows)
conn.close()
" > "$OUTPUT"

echo "Exportado $(tail -n +2 "$OUTPUT" | wc -l) emails para: $OUTPUT"
