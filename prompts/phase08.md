Tu es maintenant un auditeur indépendant senior.

Tu n'as pas pour mission de défendre le projet.

Tu dois chercher activement ses faiblesses.

Audite LOTTERY INTELLIGENCE PLATFORM comme si tu devais reprendre le projet dans trois ans.

==================================================
AUDIT DATA
==========

Cherche :

* pertes possibles ;
* doublons ;
* corruption ;
* absence de provenance ;
* absence de versioning ;
* snapshots incomplets ;
* problèmes de restauration.

==================================================
AUDIT SCIENTIFIQUE
==================

Cherche :

* data leakage ;
* look-ahead bias ;
* overfitting ;
* multiple testing ;
* p-hacking ;
* selection bias ;
* survivorship bias ;
* optimisation excessive ;
* test contamination ;
* confusion entre corrélation et pouvoir prédictif.

==================================================
AUDIT FINANCIER
===============

Vérifier :

* stake ;
* payout ;
* ROI ;
* drawdown ;
* bankroll ;
* règles de paiement ;
* calcul du profit.

==================================================
AUDIT SOFTWARE
==============

Chercher :

* couplage ;
* dette technique ;
* code mort ;
* absence de tests ;
* migrations dangereuses ;
* problèmes de concurrence ;
* idempotence ;
* sécurité.

==================================================
AUDIT PRODUCTION
================

Tester :

* backup ;
* restore ;
* panne PostgreSQL ;
* panne MinIO ;
* perte réseau ;
* reprise collector ;
* reprise worker.

==================================================
AUDIT RESEARCH MEMORY
=====================

Vérifier que les expériences anciennes peuvent être :

* retrouvées ;
* reproduites ;
* comparées ;
* invalidées ;
* expliquées.

==================================================
SORTIE

Produire :

docs/EXPERT_AUDIT.md

Classer les problèmes :

CRITICAL
HIGH
MEDIUM
LOW

Pour chaque problème :

* description ;
* preuve ;
* impact ;
* reproduction ;
* correction proposée ;
* test nécessaire.

Ne corrige pas automatiquement les problèmes CRITICAL/HIGH.

Présente d'abord le rapport d'audit.
