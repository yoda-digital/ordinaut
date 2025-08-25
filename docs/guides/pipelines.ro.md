# Pipeline-uri și Instrumente

Puterea Ordinaut provine din motorul său declarativ de pipeline, care execută o serie de pași într-un mod previzibil și fiabil.

## Structura Pipeline-ului

Un pipeline este un tablou JSON de **pași** definiți în `payload`-ul unei Sarcini. Motorul procesează acești pași în ordine, transmițând contextul între ei.

```json
{
  "payload": {
    "params": { "city": "Chisinau" },
    "pipeline": [
      {
        "id": "get_weather",
        "uses": "weather-api.get_forecast",
        "with": {"location": "${params.city}"},
        "save_as": "weather"
      },
      {
        "id": "send_alert",
        "uses": "telegram.send_message",
        "if": "steps.weather.temperature > 25",
        "with": {
          "message": "Astăzi este cald: ${steps.weather.temperature}°C"
        }
      }
    ]
  }
}
```

### Proprietăți Cheie ale Pașilor

- `id`: Un identificator unic pentru pas.
- `uses`: Adresa **Instrumentului** de executat.
- `with`: Argumentele pentru instrument (suportă variabile șablon).
- `save_as`: Cheia sub care se salvează rezultatul pasului.
- `if`: O expresie condițională [JMESPath](https://jmespath.org/) pentru a omite pasul.
- `timeout_seconds`: Timeout opțional pentru apelul instrumentului.
- `max_retries`: Număr opțional de reîncercări pentru pas.

## Variabile Șablon

Puteți insera dinamic date în blocul `with` folosind variabile șablon:

- **`${params.variable_name}`**: Accesează parametrii din `payload.params`.
- **`${steps.step_id.output_field}`**: Accesează rezultatul unui pas anterior.
- **`${now}`**: Furnizează timestamp-ul UTC curent.

## Execuția Instrumentelor (Simulată)

Instrumentele sunt blocurile de construcție ale pipeline-urilor. Cu toate acestea, este crucial să înțelegeți că motorul de bază Ordinaut **simulează** execuția instrumentelor.

!!! warning "Instrumentele Nu Sunt Executate de Motorul Principal"
    Când executorul de pipeline întâlnește un pas cu un câmp `uses`, acesta:
    1.  Redă șabloanele de intrare din blocul `with`.
    2.  Înregistrează în jurnal că un apel la instrument este **simulat**.
    3.  Generează un obiect de ieșire simulat.
    4.  Dacă `save_as` este prezent, salvează această ieșire simulată în context.

    Motorul **nu** are un catalog de instrumente și nu execută cod extern. Implementarea reală a instrumentelor trebuie să fie construită ca **servicii de extensie separate**.

## Gestionarea Erorilor

Dacă un pas eșuează (de exemplu, o eroare de redare a șablonului), motorul va respecta politica `max_retries`. Dacă toate reîncercările eșuează, întreaga rulare a pipeline-ului este marcată ca `eșuată`, iar detaliile erorii sunt înregistrate în obiectul **Rulare**.