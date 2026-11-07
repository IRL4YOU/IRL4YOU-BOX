#!/bin/bash
# ROCK 5B Plus: Lüfterregelung für den ALUKÜHLER (schwächerer Wärmeübergang, deshalb früher und steiler). Läuft der Lüfter, dreht er mindestens mit 182 (ROCK 5B+, Kernel 6.1, gemessen am 6. Nov: 170 und 178 stehen oder fiepen, 180 grenzwertig, 182 und mehr laufen).
# Ein ab 48 Grad, aus unter 44 Grad. Stufenlos 182 bis 255 von 48 bis 66 Grad, Temperatur über etwa 6 s geglättet.
# Notfall: ab 66 Grad (ungeglaettet) oder bei Fehlern volle Leistung. Fuer den Kupferkuehler: kupfer/rock5bplus-fan-kupfer.sh.
set -euo pipefail
# Nur auf der ROCK 5B+ (die Orange Pi 5 Plus hat auch einen PWM-Luefter, den der Kernel selbst regelt): sonst nichts anfassen
grep -a -q -F -e "ROCK 5B+" -e "ROCK 5B Plus" "${MODEL_FILE:-/proc/device-tree/model}" 2>/dev/null || { echo "Keine ROCK 5B+: Luefterregelung nicht gestartet" >&2; exit 0; }
# Kurve dieser Variante in Tausendstel Grad (1000 = 1 Grad): an ab ON, aus unter OFF, voll bei FULL, Notfall ab EMERG; MIN_PWM = kleinste Drehzahl, mit der der Lüfter sicher läuft
ON_MC=48000; OFF_MC=44000; FULL_MC=66000; EMERG_MC=66000; MIN_PWM=182
shopt -s nullglob
fan_paths=()
for device in /sys/class/hwmon/hwmon*; do
  [[ $(cat "$device/name") == pwmfan ]] || continue
  [[ $(readlink -f "$device/device") == /sys/devices/platform/pwm-fan ]] || continue
  [[ -w $device/pwm1 ]] && fan_paths+=("$device/pwm1")
done
[[ ${#fan_paths[@]} == 1 ]] || { echo 'Luefter nicht eindeutig gefunden' >&2; exit 1; }
pwm=${fan_paths[0]}
failsafe() { printf '255\n' > "$pwm" || true; }
trap failsafe EXIT
trap 'exit 0' TERM INT
sensor_paths=()
for device in /sys/class/thermal/thermal_zone*; do
  [[ $(cat "$device/type") == soc-thermal ]] && sensor_paths+=("$device/temp")
done
[[ ${#sensor_paths[@]} == 1 ]] || { echo 'SoC-Sensor nicht eindeutig gefunden' >&2; exit 1; }
sensor=${sensor_paths[0]}
echo "Luefterregelung (stufenlos) gestartet: $pwm; Sensor $sensor"
# Die Kuehlsteuerung des Kernels wuerde denselben Luefter sonst stufenweise zurueckstellen und erzeugt dabei dauernd Systemmeldungen.
# Darum ist die Waermezone im Betrieb ausgeschaltet. Ab 80 Grad schaltet sie sich als Sicherung (Drosselung) wieder ein, unter 76 Grad wieder aus.
ZONE=/sys/class/thermal/thermal_zone0
echo 84000 > $ZONE/trip_point_0_temp 2>/dev/null || true
echo step_wise > $ZONE/policy 2>/dev/null || true
zmode=disabled; echo disabled > $ZONE/mode 2>/dev/null || true
trap 'echo enabled > $ZONE/mode 2>/dev/null; failsafe' EXIT
printf '255\n' > "$pwm"; sleep 4
avg=-1; cur=255; first=1                             # first: nach dem Start sofort auf den Sollwert statt langsam von 255 herunter
while true; do
  t=$(cat "$sensor")
  [[ $t =~ ^[0-9]+$ ]] && ((t > 0 && t < 150000)) || { echo 'Ungueltiger Temperaturwert: volle Luefterleistung' >&2; exit 1; }
  if ((avg < 0)); then avg=$t; else avg=$(( (avg * 3 + t) / 4 )); fi
  if ((t >= 80000)); then want_mode=enabled; elif ((t < 76000)); then want_mode=disabled; else want_mode=$zmode; fi
  if [[ $want_mode != "$zmode" ]]; then zmode=$want_mode; echo "$zmode" > $ZONE/mode 2>/dev/null || true; fi
  if ((t >= EMERG_MC)); then
    nxt=255
  else
    if ((avg >= ON_MC || (cur > 0 && avg >= OFF_MC))); then
      x=$avg; ((x < ON_MC)) && x=$ON_MC; ((x > FULL_MC)) && x=$FULL_MC
      want=$(( MIN_PWM + (x - ON_MC) * (255 - MIN_PWM) / (FULL_MC - ON_MC) ))
    else
      want=0
    fi
    if ((first)); then
      nxt=$want
    elif ((want == 0)); then
      if ((cur > MIN_PWM)); then nxt=$((cur - 3)); ((nxt < MIN_PWM)) && nxt=$MIN_PWM; else nxt=0; fi
    elif ((cur == 0)); then
      printf '255\n' > "$pwm"; sleep 4; nxt=$want       # kurzer Anlaufstoss nur nach Stillstand
    elif ((want > cur)); then
      nxt=$((cur + 25)); ((nxt > want)) && nxt=$want
    elif ((want < cur)); then
      nxt=$((cur - 3)); ((nxt < want)) && nxt=$want
    else
      nxt=$cur
    fi
  fi
  cur=$nxt; first=0
  # Der Kernel hat eine eigene Kuehlsteuerung fuer denselben Luefter und stellt die Stufe zwischendurch zurueck
  # (daher frueher das An/Aus). Deshalb den Sollwert mehrmals pro Sekunde neu setzen: Rueckstellungen dauern so nur Bruchteile.
  for _ in 1 2 3 4 5 6 7 8; do
    printf '%s\n' "$cur" > "$pwm"
    sleep 0.25
  done
done
