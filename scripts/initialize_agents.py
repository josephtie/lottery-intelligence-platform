#!/usr/bin/env python3
"""Initialize the 10 autonomous agent profiles for Lottery Edge Lab."""

import os
import sys
from datetime import datetime

import psycopg
from dotenv import load_dotenv

load_dotenv()

# Agent profiles
AGENT_PROFILES = [
    {
        "code": "HUNTER",
        "display_name": "The Hunter",
        "generation": 1,
        "status": "ACTIVE",
        "operational_level": "DECISION",
        "mission": "Détecteur de signaux - Il cherche les fréquences inhabituelles, les variations temporelles, les répétitions et les changements de comportement statistique.",
        "specialties": "Signal detection, frequency analysis, temporal patterns, statistical anomalies",
        "objectives": "Trouver un signal stable derrière ce qui paraît aléatoire",
        "preferred_methods": "Statistical anomaly detection, time series analysis, pattern recognition",
        "initial_capital": 100000,
    },
    {
        "code": "QUANT",
        "display_name": "The Quant",
        "generation": 1,
        "status": "ACTIVE",
        "operational_level": "RESEARCH",
        "mission": "Mathématicien - Il construit ses propres modèles probabilistes, étudie les dépendances, teste les distributions et quantifie l'incertitude.",
        "specialties": "Probability models, dependency analysis, distribution testing, uncertainty quantification",
        "objectives": "Déterminer si les observations sont réellement incompatibles avec le hasard",
        "preferred_methods": "Bayesian inference, Monte Carlo simulation, hypothesis testing",
        "initial_capital": 100000,
    },
    {
        "code": "ARCHITECT",
        "display_name": "The Architect",
        "generation": 1,
        "status": "ACTIVE",
        "operational_level": "EVOLUTION",
        "mission": "Créateur de combinaisons - Il compose ses propres ensembles de modèles, compare leurs désaccords et apprend quelles combinaisons apportent une information supplémentaire.",
        "specialties": "Model ensemble, combination optimization, disagreement analysis",
        "objectives": "Déterminer si plusieurs méthodes réunies font mieux que chacune séparément",
        "preferred_methods": "Ensemble methods, meta-learning, model combination",
        "initial_capital": 100000,
    },
    {
        "code": "EXPLORER",
        "display_name": "The Explorer",
        "generation": 1,
        "status": "ACTIVE",
        "operational_level": "RESEARCH",
        "mission": "Chercheur de structures - Il explore librement les relations entre numéros, positions, inversions, Calling/Image et structures encore inconnues.",
        "specialties": "Structural discovery, pattern exploration, relationship mapping",
        "objectives": "Trouver une hypothèse originale personne n'a encore correctement testée",
        "preferred_methods": "Graph analysis, clustering, unsupervised learning",
        "initial_capital": 100000,
    },
    {
        "code": "SIMULATOR",
        "display_name": "The Simulator",
        "generation": 1,
        "status": "ACTIVE",
        "operational_level": "RESEARCH",
        "mission": "Expérimentateur - Il génère des milliers de variantes, les confronte à des références aléatoires et conserve les candidates qui résistent aux tests.",
        "specialties": "Variant generation, random baseline testing, robustness evaluation",
        "objectives": "Déterminer si un résultat est exceptionnel ou apparaît régulièrement par hasard",
        "preferred_methods": "Simulation, bootstrapping, permutation testing",
        "initial_capital": 100000,
    },
    {
        "code": "CONTRARIAN",
        "display_name": "The Contrarian",
        "generation": 1,
        "status": "ACTIVE",
        "operational_level": "DECISION",
        "mission": "Penseur indépendant - Il remet en cause le consensus, recherche des hypothèses opposées et teste des sélections différentes de celles des autres agents.",
        "specialties": "Consensus analysis, opposing hypothesis testing, contrarian strategies",
        "objectives": "Déterminer si les autres parieurs partagent tous la même erreur",
        "preferred_methods": "Consensus deviation, contrarian betting, crowd analysis",
        "initial_capital": 100000,
    },
    {
        "code": "EVOLVER",
        "display_name": "The Evolver",
        "generation": 1,
        "status": "ACTIVE",
        "operational_level": "EVOLUTION",
        "mission": "Évolutionniste - Il crée des générations de stratégies, modifie les paramètres, croise des méthodes et retire les variantes durablement faibles.",
        "specialties": "Strategy evolution, parameter optimization, crossover methods",
        "objectives": "Découvrir quelles nouvelles stratégies peuvent être créées à partir des expériences précédentes",
        "preferred_methods": "Genetic algorithms, evolution strategies, mutation operators",
        "initial_capital": 100000,
    },
    {
        "code": "BAYESIAN",
        "display_name": "The Bayesian",
        "generation": 1,
        "status": "ACTIVE",
        "operational_level": "DECISION",
        "mission": "Apprentissage incertain - Il actualise ses estimations à mesure que les données arrivent et distingue les signaux solides des résultats trop incertains.",
        "specialties": "Bayesian updating, uncertainty quantification, sequential learning",
        "objectives": "Déterminer quelle confiance les preuves justifient aujourd'hui",
        "preferred_methods": "Bayesian inference, probabilistic programming, uncertainty estimation",
        "initial_capital": 100000,
    },
    {
        "code": "CAPITALIST",
        "display_name": "The Capitalist",
        "generation": 1,
        "status": "ACTIVE",
        "operational_level": "DECISION",
        "mission": "Gestionnaire de capital - Il compare les marchés, les cotes, les mises et les risques. Il cherche à maximiser la rentabilité nette plutôt que le simple nombre de résultats gagnants.",
        "specialties": "Capital management, risk-reward analysis, ROI optimization",
        "objectives": "Déterminer si une méthode est rentable après les pertes et les mises",
        "preferred_methods": "Kelly criterion, position sizing, risk management",
        "initial_capital": 100000,
    },
    {
        "code": "GRANDMASTER",
        "display_name": "The Grandmaster",
        "generation": 1,
        "status": "ACTIVE",
        "operational_level": "EVOLUTION",
        "mission": "Stratège autonome - Il dispose d'une liberté de recherche maximale. Il peut créer des hypothèses, appeler plusieurs modèles, concevoir de nouvelles stratégies et apprendre des travaux des neuf autres profils.",
        "specialties": "Meta-strategy, cross-agent learning, synthetic approaches",
        "objectives": "Trouver quelle approche, y compris une approche non imaginée, mérite d'être testée",
        "preferred_methods": "Meta-learning, strategy synthesis, cross-agent collaboration",
        "initial_capital": 100000,
    },
]


def get_dsn() -> str:
    """Get database connection string from environment."""
    host = os.environ.get("LOTTERY_DATABASE_HOST", "localhost")
    port = os.environ.get("LOTTERY_DATABASE_PORT", "5432")
    database = os.environ.get("LOTTERY_DATABASE_NAME", "lottery_platform")
    user = os.environ.get("LOTTERY_DATABASE_USER", "directus")
    password = os.environ.get("LOTTERY_DATABASE_PASSWORD", "")
    return f"host={host} port={port} dbname={database} user={user} password={password}"


def initialize_agents():
    """Initialize the 10 agent profiles in the database."""
    dsn = get_dsn()
    
    with psycopg.connect(dsn, autocommit=True) as conn:
        for profile in AGENT_PROFILES:
            # Check if agent already exists
            existing = conn.execute(
                "SELECT agent_id FROM edge_lab.agents WHERE code = %s",
                (profile["code"],)
            ).fetchone()
            
            if existing:
                print(f"Agent {profile['code']} already exists, skipping...")
                continue
            
            # Insert agent
            conn.execute(
                """INSERT INTO edge_lab.agents 
                   (code, display_name, generation, status, mission, specialties, 
                    objectives, preferred_methods, operational_level, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    profile["code"],
                    profile["display_name"],
                    profile["generation"],
                    profile["status"],
                    profile["mission"],
                    profile["specialties"],
                    profile["objectives"],
                    profile["preferred_methods"],
                    profile["operational_level"],
                    datetime.now(),
                    datetime.now(),
                )
            )
            
            # Get the agent_id
            agent_id = conn.execute(
                "SELECT agent_id FROM edge_lab.agents WHERE code = %s",
                (profile["code"],)
            ).fetchone()[0]
            
            # Initialize capital
            conn.execute(
                """INSERT INTO edge_lab.agent_capital 
                   (agent_id, initial_capital, current_capital, updated_at)
                   VALUES (%s, %s, %s, %s)""",
                (agent_id, profile["initial_capital"], profile["initial_capital"], datetime.now())
            )
            
            # Initialize memory compartments
            conn.execute(
                """INSERT INTO edge_lab.memory_identity (agent_id, created_at) VALUES (%s, %s)""",
                (agent_id, datetime.now())
            )
            
            print(f"✓ Created agent: {profile['code']} - {profile['display_name']}")
        
        print(f"\n✅ Successfully initialized {len(AGENT_PROFILES)} agents")
        print("\nAgent Summary:")
        conn.execute("REFRESH MATERIALIZED VIEW edge_lab.agent_summary")
        summary = conn.execute("SELECT * FROM edge_lab.agent_summary ORDER BY code").fetchall()
        for row in summary:
            print(f"  {row['code']:12} | {row['display_name']:20} | {row['status']:8} | {row['current_capital']:10,.0f} FCFA")


if __name__ == "__main__":
    try:
        initialize_agents()
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
