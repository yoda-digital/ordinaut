# API-ul de Sarcini (Tasks)

API-ul de Sarcini este interfața principală pentru crearea, gestionarea și monitorizarea fluxurilor de lucru automate.

## `POST /tasks`

Creează o nouă sarcină programată. Pentru o listă completă de câmpuri, consultați documentația în limba engleză.

## `GET /tasks`

Afișează sarcinile cu filtrare opțională. Parametrii includ `status`, `created_by`, `schedule_kind`, `limit`, și `offset`.

## `GET /tasks/{id}`

Recuperează detaliile complete ale unei sarcini specifice după UUID-ul său.

## `PUT /tasks/{id}`

Actualizează o sarcină existentă. Doar câmpurile furnizate în corpul cererii vor fi actualizate.

## `POST /tasks/{id}/run_now`

Declanșează o execuție imediată, unică, a unei sarcini.

## `POST /tasks/{id}/snooze`

Amână următoarea execuție programată a unei sarcini.

## `POST /tasks/{id}/pause`

Întrerupe o sarcină, prevenind orice rulări programate viitoare.

## `POST /tasks/{id}/resume`

Reia o sarcină întreruptă anterior.

## `POST /tasks/{id}/cancel`

Anulează permanent o sarcină. Această acțiune nu poate fi anulată.