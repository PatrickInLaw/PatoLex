# Office-hours scale-UP: return the 5090 to its full off-hours worker count.
# Scheduled ~17:00 Mon-Fri (end of office hours). Scale-up is immediate (no drain
# lag) -- the supervisor adds workers one at a time into the running set.
# VALUE: 3 = proven optimal. Change to 4 ONLY if the desynced-4 throughput test
# shows a real gain (a 4th worker added live, not 4 started at once).
Set-Content -Path 'C:\Users\patolex\PatoLex-scratch\max_workers.txt' -Value 3 -Encoding ascii
