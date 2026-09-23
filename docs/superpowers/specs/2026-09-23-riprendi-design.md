# riprendi — riprendere una sessione di Claude Code quando il limite si sblocca

Data: 2026-09-23.

## Perche'

Alessio: *"un'app che quando finisce i crediti di sessione corrente permette di ricominciare appena
si riavviano"*. Oggi una sessione di lavoro si e' fermata sul limite ("your session limit resets
11am") e il lavoro e' ripartito solo quando qualcuno l'ha rilanciato a mano.

Dalle domande:
- **Scopo:** riprende **da sola** il lavoro, senza nessuno davanti.
- **Permessi:** la sessione ripresa gira in `--permission-mode auto`.
- **Approccio:** un **sorvegliante** in background; Alessio continua a usare `claude` come sempre.
- **Quali sessioni:** **solo quelle marcate** da lui.

Successo = una sessione marcata che si ferma sul limite riparte da sola pochi minuti dopo lo sblocco,
con una notifica sul desktop, senza mai sovrapporsi a una ripresa fatta a mano e senza ripartire
all'infinito se il limite non si sblocca.

## Fatti verificati

- `claude` 2.1.280 ha `--resume <id>`, `-p/--print` (non interattivo) e
  `--permission-mode {acceptEdits,auto,bypassPermissions,manual,dontAsk,plan}`.
- Le sessioni stanno in `~/.claude/projects/<cartella>/<session-id>.jsonl`, una riga JSON per
  evento; gli agenti figli stanno in `<session-id>/subagents/` e **non** vanno considerati.
- Ogni riga ha `cwd` e `sessionId`. Il nome della cartella deriva dal percorso, ma la regola esatta
  non e' documentata: la sessione di una cartella si trova **leggendo `cwd`**, non ricostruendo il nome.
- Un limite raggiunto e' scritto cosi' (caso reale del 2026-09-23):
  `{"type":"assistant","isApiErrorMessage":true,"error":"rate_limit",...,"message":{"content":[{"type":"text","text":"You've hit your monthly spend limit · raise it at … · your session limit resets 11am (Europe/Rome)"}]}}`.

## Comandi

| Comando | Effetto |
|---|---|
| `riprendi segui [session-id]` | Segue la sessione indicata; senza id, la sessione **modificata piu' di recente** il cui `cwd` e' la cartella corrente |
| `riprendi smetti [session-id]` | Smette di seguirla (senza id: quella della cartella corrente, se seguita) |
| `riprendi stato` | Per ogni sessione seguita: cartella, stato (`attiva` / `bloccata fino a HH:MM` / `in ripresa` / `ferma: troppi tentativi`), riprese fatte |
| `riprendi sorveglia` | Il ciclo del sorvegliante (lo lancia systemd) |
| `riprendi installa` | Scrive e abilita il servizio `systemd --user` `riprendi.service` |

Stato persistente in `~/.local/state/riprendi/state.json`, log in `~/.local/state/riprendi/logs/`.

## Sorvegliante

Ogni 60 secondi, per ogni sessione seguita:

1. Legge l'**ultimo evento significativo** del file (ultima riga di tipo `user` o `assistant`).
2. Se e' un errore di limite (`isApiErrorMessage` vero ed `error == "rate_limit"`), la sessione e'
   **bloccata**. L'orario di sblocco si ricava dal testo:
   - `resets 11am (Europe/Rome)`, `resets 3:30pm (Europe/Rome)`, `resets 15:00` → il primo
     momento futuro con quell'ora (oggi, altrimenti domani), nel fuso indicato o in quello locale;
   - qualunque altro testo → **30 minuti** dopo l'errore, e poi di nuovo ogni 30 minuti.
3. Allo sblocco **+ 2 minuti**, se nessun'altra condizione lo impedisce, riprende.

**Non riprende** se:
- il file della sessione e' stato modificato **dopo** la riga d'errore (qualcuno l'ha gia' ripresa,
  o c'e' una sessione interattiva attiva);
- c'e' gia' una ripresa in corso per quella sessione;
- ha gia' fatto **3 riprese consecutive** finite di nuovo sul limite: stato `ferma: troppi tentativi`
  e notifica. Una ripresa che produce lavoro (l'ultimo evento non e' piu' un errore) azzera il conto.

## Ripresa

Nella cartella `cwd` della sessione:

```
claude --resume <id> -p "Il limite di utilizzo si e' sbloccato: continua da dove eri rimasto. Se il lavoro era finito, dillo e fermati." --permission-mode auto
```

- stdout/stderr in `logs/<id>-<timestamp>.log`;
- notifica `notify-send` all'avvio ("Ripresa: <cartella>") e alla fine ("Finita" oppure "Di nuovo
  bloccata fino a HH:MM");
- se `claude` non esiste o esce con errore che non e' un limite: stato `errore`, notifica, niente
  nuovi tentativi finche' Alessio non rilancia `riprendi segui`.

## Sicurezza

- Nessuna credenziale letta o salvata: usa il login gia' presente di `claude`.
- `auto` blocca le azioni rischiose; `bypassPermissions` non e' mai usato.
- Il file di stato contiene solo id, percorsi e orari.

## Verifica

`unittest` (stdlib), senza lanciare `claude` davvero: riconoscimento dell'errore di limite; lettura
dell'orario nei formati sopra, compreso il passaggio al giorno dopo; ultimo evento significativo
(righe troncate a meta' scrittura ignorate); `segui` che sceglie la sessione giusta dalla `cwd`;
decisione "riprendere si'/no" (modificata dopo l'errore, ripresa in corso, tetto a 3, azzeramento);
comando di ripresa costruito esattamente come sopra. Prova finale dal vivo con un `claude` finto
nel `PATH` e una sessione di prova.

## Fuori dallo scope

Notifiche sul telefono, ripresa degli agenti figli, funzionamento a PC spento, riprese di sessioni
non marcate.
