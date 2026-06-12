# Changelog

eduPersona kent nog geen formele releases. In dit bestand noteren we de
noemenswaardige wijzigingen, met de meest recente bovenaan.

## v0.2 — juni 2026 - pivot naar 'persona'

eduPersona is omgebouwd van een **rol-/gastgebaseerd** model naar **persona's**, met de **uitnodiging** als centrale entiteit. Het
*soort* gast (de persona) is nu het organiserende begrip. De redenatie is dat een gast niet afzonderlijk hoeft te worden geverifieerd voor elke *rol* die aan 
hem/haar wordt toegekend, maar voor elk *type* relatie dat hij/zij met de instelling heeft. 

Na deze wijziging bepaalt de *persona* het stappenplan, de mailtemplate en de teruggekoppelde
gegevenssets. Rollen, autorisaties en geldigheidsvensters horen voortaan
volledig in de IAM-keten van de instelling thuis, niet in eduPersona.

### Waarom deze pivot

- **Scherpere scope, minder duplicatie.** De oude opzet (gasten, rollen,
  roltoekenningen) dupliceerde functionaliteit die thuishoort in de
  IAM/IGA van de instelling. eduPersona's eigenlijke meerwaarde is het *betrouwbaar
  verifiëren en koppelen* van een eduID aan een instellingsidentiteit — niet het beheren
  van rollen en autorisaties. Door alles rond rollen weg te laten wordt die grens helder
  en blijft eduPersona klein.
- **De persona sluit aan op de praktijk.** Wat de onboarding bepaalt is niet de rol maar
  het *soort* gast: een gastdocent moet iets anders aantonen dan een alumnus. De persona
  maakt dat expliciet en configureerbaar; rol- en autorisatietoekenning blijft
  aan de IAM-kant.
- **Eén entiteit = eenvoudiger en onderhoudbaarder.** Met de uitnodiging als enige
  first-class entiteit verdwijnt veel model- en UI-complexiteit (junction-tabellen,
  rol-CRUD, een aparte gastenportal). Minder code, minder oppervlak om te onderhouden —
  passend bij een PoC.
- **Webhook-callback i.p.v. SCIM groep-/rol-sync.** De kern van wat eduPersona oplevert
  is een gebeurtenis: "deze gast is geverifieerd en klaar". Een eenvoudige callback met
  de geverifieerde gegevens past daar beter bij dan het synchroniseren van rollen en
  groepen — dat laatste is en blijft werk voor de IAM. SCIM blijft optioneel beschikbaar
  voor wie de bare user tóch via SCIM wil ontvangen.

### Toegevoegd

- **Persona-contract**: getypeerde `PersonaConfig` + loader/validator
  (`domain/persona.py`, `services/persona_loader.py`), per tenant gedefinieerd onder
  `tenants.<t>.personas`. Zie [`docs/personas.md`](docs/personas.md).
- **Webhook-callback** als terugkoppeling: envelope-builder + delivery-state-machine
  (4xx terminaal, 5xx/netwerk → retry met exponentiële back-off, achtergrond-retry-loop).
  Zie [`docs/callback_api.md`](docs/callback_api.md).
- **Simulator-pagina** (`/m/{tenant}/simulator`) om interactief persona-uitnodigingen
  aan te maken.
- **Invitation expiry**: per-tenant verloopduur, API-override, claim-time sweep en een
  `POST /maintenance`-endpoint (cron) dat verlopen uitnodigingen opruimt.
- **Register-gate**: een expliciete bevestigingsstap aan het eind van het stappenplan,
  gevolgd door een per-persona **welkomstscherm**.
- **Step cards** `VerifyMfaStep`, `VerifyMobileStep`, `VerifyAlumniDb` — auto-registrerend
  onder `steps/cards/` (de uitbreidingslaag).

### Gewijzigd

- `Invitation` is nu de enige first-class entiteit, met persona-velden (`persona_key`,
  `persona_params`, `step_outputs`, `callback_url`, sender, expiry) en `WebhookDelivery`
  eraan gekoppeld.
- `guest_id` als verplicht veld, afgebeeld op SCIM `externalId`).
- De accept-flow is persona-gestuurd en reactief: `/accept[/{code}]` is tenant-loos,
  de tenant wordt uit de uitnodigingscode afgeleid.
- De invitations-admin draait op ng_rdm (ViewStack → ListTable → DetailCard).
- **SCIM** is teruggebracht tot één optionele, dormant *bare-user* push bij afronding —
  geen synchronisatie van rollen of groepen meer.
- Post-pivot opschoning: i18n, config-validatie bij startup, UI-error-discipline.

### Verwijderd

- De modellen `Guest`, `Role`, `RoleAssignment`, `InvitationRoleAssignment` en
  `GuestAttribute`.
- De rol-/gast-beheerpagina's en de `/apps`-portal (vervangen door het welkomstscherm).
- De oude rol-gebaseerde API (`guests`, `roles`, `role assignments`, `create_invite_role`)
  en de SCIM groep-/rol-synchronisatie.
- `FinalizeStep` (vervangen door de Register-gate + het welkomstscherm).

### Migratie

Het databaseschema is gewijzigd. Voor een PoC is een verse setup het eenvoudigst
(de SQLite-database wordt bij de eerste start aangemaakt). Verwijder zonodig `edupersona.db` voordat je de server start.