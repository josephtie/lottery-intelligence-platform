Tu es responsable de la certification finale de LOTTERY INTELLIGENCE PLATFORM v1.0.

La plateforme ne peut être déclarée prête que si elle satisfait les critères suivants.

==================================================
DATA
====

[ ] RAW immutable
[ ] PostgreSQL source of truth
[ ] provenance complète
[ ] dataset versioning
[ ] snapshots
[ ] corrections historisées
[ ] backups
[ ] restore testé

==================================================
RESEARCH
========

[ ] feature versioning
[ ] model registry
[ ] experiment registry
[ ] reproducibility
[ ] anti-leakage tests
[ ] walk-forward
[ ] OOS
[ ] prospective

==================================================
STRATEGY
========

[ ] Turbo versionné
[ ] payout rules versionnées
[ ] backtesting
[ ] bankroll simulation
[ ] profitability
[ ] drawdown
[ ] losing streak
[ ] NO_EDGE

==================================================
KNOWLEDGE
=========

[ ] hypothesis registry
[ ] findings
[ ] rejected hypotheses
[ ] similar experiment detection
[ ] research history

==================================================
PRODUCTION
==========

[ ] Docker deployment
[ ] healthchecks
[ ] structured logs
[ ] monitoring
[ ] security
[ ] backup
[ ] restore

==================================================
CERTIFICATION

Exécuter tous les tests.

Produire :

docs/RELEASE_CERTIFICATION.md

avec :

* version ;
* git commit ;
* schema version ;
* dataset version ;
* tests ;
* coverage ;
* infrastructure ;
* known limitations ;
* security status ;
* recovery test ;
* research validation status.

Ne jamais déclarer le système "profitable".

La certification signifie uniquement que la plateforme est techniquement et méthodologiquement prête à poursuivre ses recherches.

Toute affirmation économique doit être accompagnée de ses données, de sa période et de son protocole.
