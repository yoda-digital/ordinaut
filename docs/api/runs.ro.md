# API-ul de Rulări (Runs)

API-ul de Rulări permite monitorizarea istoricului de execuție al sarcinilor.

---

## `GET /runs`

Afișează rulările de execuție ale sarcinilor cu filtrare opțională. Parametrii includ `task_id`, `success`, `start_time`, `end_time`, `limit` și `offset`.

---

## `GET /runs/{run_id}`

Recuperează rezultatele detaliate ale unei singure rulări de sarcină.

---

## `GET /task/{task_id}/latest`

Recuperează cea mai recentă rulare pentru o sarcină specifică.

---

## `GET /task/{task_id}/stats`

Recuperează statistici de execuție pentru o sarcină specifică.

---

## `GET /stats/summary`

Recuperează statistici de execuție la nivel de sistem pentru toate sarcinile.