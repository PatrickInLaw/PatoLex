# Office-hours scale-DOWN: drop the 5090 to 1 worker so the GPU stays cool/quiet
# during client meetings (the 5090 sits under the desk). Scheduled ~07:30 Mon-Fri
# -- a 30-min lead so a volume claimed just before the cutoff drains before 08:00.
# The supervisor reads max_workers.txt every ~30s and drains surplus workers
# gracefully (they finish their current volume, then exit -- never killed).
Set-Content -Path 'C:\Users\patolex\PatoLex-scratch\max_workers.txt' -Value 1 -Encoding ascii
