-- Initialize the 10 autonomous agent profiles for Lottery Edge Lab

-- Insert agents
INSERT INTO edge_lab.agents (agent_id, code, display_name, generation, status, mission, specialties, objectives, preferred_methods, operational_level, created_at, updated_at) VALUES
(gen_random_uuid(), 'HUNTER', 'The Hunter', 1, 'ACTIVE', 'Détecteur de signaux - Il cherche les fréquences inhabituelles, les variations temporelles, les répétitions et les changements de comportement statistique.', '["Signal detection", "frequency analysis", "temporal patterns", "statistical anomalies"]'::jsonb, '["Trouver un signal stable derrière ce qui paraît aléatoire"]'::jsonb, '["Statistical anomaly detection", "time series analysis", "pattern recognition"]'::jsonb, 'DECISION', NOW(), NOW()),
(gen_random_uuid(), 'QUANT', 'The Quant', 1, 'ACTIVE', 'Mathématicien - Il construit ses propres modèles probabilistes, étudie les dépendances, teste les distributions et quantifie l''incertitude.', '["Probability models", "dependency analysis", "distribution testing", "uncertainty quantification"]'::jsonb, '["Déterminer si les observations sont réellement incompatibles avec le hasard"]'::jsonb, '["Bayesian inference", "Monte Carlo simulation", "hypothesis testing"]'::jsonb, 'RESEARCH', NOW(), NOW()),
(gen_random_uuid(), 'ARCHITECT', 'The Architect', 1, 'ACTIVE', 'Créateur de combinaisons - Il compose ses propres ensembles de modèles, compare leurs désaccords et apprend quelles combinaisons apportent une information supplémentaire.', '["Model ensemble", "combination optimization", "disagreement analysis"]'::jsonb, '["Déterminer si plusieurs méthodes réunies font mieux que chacune séparément"]'::jsonb, '["Ensemble methods", "meta-learning", "model combination"]'::jsonb, 'EVOLUTION', NOW(), NOW()),
(gen_random_uuid(), 'EXPLORER', 'The Explorer', 1, 'ACTIVE', 'Chercheur de structures - Il explore librement les relations entre numéros, positions, inversions, Calling/Image et structures encore inconnues.', '["Structural discovery", "pattern exploration", "relationship mapping"]'::jsonb, '["Trouver une hypothèse originale personne n''a encore correctement testée"]'::jsonb, '["Graph analysis", "clustering", "unsupervised learning"]'::jsonb, 'RESEARCH', NOW(), NOW()),
(gen_random_uuid(), 'SIMULATOR', 'The Simulator', 1, 'ACTIVE', 'Expérimentateur - Il génère des milliers de variantes, les confronte à des références aléatoires et conserve les candidates qui résistent aux tests.', '["Variant generation", "random baseline testing", "robustness evaluation"]'::jsonb, '["Déterminer si un résultat est exceptionnel ou apparaît régulièrement par hasard"]'::jsonb, '["Simulation", "bootstrapping", "permutation testing"]'::jsonb, 'RESEARCH', NOW(), NOW()),
(gen_random_uuid(), 'CONTRARIAN', 'The Contrarian', 1, 'ACTIVE', 'Penseur indépendant - Il remet en cause le consensus, recherche des hypothèses opposées et teste des sélections différentes de celles des autres agents.', '["Consensus analysis", "opposing hypothesis testing", "contrarian strategies"]'::jsonb, '["Déterminer si les autres parieurs partagent tous la même erreur"]'::jsonb, '["Consensus deviation", "contrarian betting", "crowd analysis"]'::jsonb, 'DECISION', NOW(), NOW()),
(gen_random_uuid(), 'EVOLVER', 'The Evolver', 1, 'ACTIVE', 'Évolutionniste - Il crée des générations de stratégies, modifie les paramètres, croise des méthodes et retire les variantes durablement faibles.', '["Strategy evolution", "parameter optimization", "crossover methods"]'::jsonb, '["Découvrir quelles nouvelles stratégies peuvent être créées à partir des expériences précédentes"]'::jsonb, '["Genetic algorithms", "evolution strategies", "mutation operators"]'::jsonb, 'EVOLUTION', NOW(), NOW()),
(gen_random_uuid(), 'BAYESIAN', 'The Bayesian', 1, 'ACTIVE', 'Apprentissage incertain - Il actualise ses estimations à mesure que les données arrivent et distingue les signaux solides des résultats trop incertains.', '["Bayesian updating", "uncertainty quantification", "sequential learning"]'::jsonb, '["Déterminer quelle confiance les preuves justifient aujourd''hui"]'::jsonb, '["Bayesian inference", "probabilistic programming", "uncertainty estimation"]'::jsonb, 'DECISION', NOW(), NOW()),
(gen_random_uuid(), 'CAPITALIST', 'The Capitalist', 1, 'ACTIVE', 'Gestionnaire de capital - Il compare les marchés, les cotes, les mises et les risques. Il cherche à maximiser la rentabilité nette plutôt que le simple nombre de résultats gagnants.', '["Capital management", "risk-reward analysis", "ROI optimization"]'::jsonb, '["Déterminer si une méthode est rentable après les pertes et les mises"]'::jsonb, '["Kelly criterion", "position sizing", "risk management"]'::jsonb, 'DECISION', NOW(), NOW()),
(gen_random_uuid(), 'GRANDMASTER', 'The Grandmaster', 1, 'ACTIVE', 'Stratège autonome - Il dispose d''une liberté de recherche maximale. Il peut créer des hypothèses, appeler plusieurs modèles, concevoir de nouvelles stratégies et apprendre des travaux des neuf autres profils.', '["Meta-strategy", "cross-agent learning", "synthetic approaches"]'::jsonb, '["Trouver quelle approche, y compris une approche non imaginée, mérite d''être testée"]'::jsonb, '["Meta-learning", "strategy synthesis", "cross-agent collaboration"]'::jsonb, 'EVOLUTION', NOW(), NOW())
ON CONFLICT (code) DO NOTHING;

-- Initialize capital for each agent (100,000 FCFA each)
INSERT INTO edge_lab.agent_capital (capital_id, agent_id, initial_capital, current_capital)
SELECT gen_random_uuid(), a.agent_id, 100000, 100000
FROM edge_lab.agents a
WHERE a.code IN ('HUNTER', 'QUANT', 'ARCHITECT', 'EXPLORER', 'SIMULATOR', 'CONTRARIAN', 'EVOLVER', 'BAYESIAN', 'CAPITALIST', 'GRANDMASTER')
ON CONFLICT DO NOTHING;

-- Initialize memory compartments for each agent
INSERT INTO edge_lab.memory_identity (memory_id, agent_id)
SELECT gen_random_uuid(), a.agent_id
FROM edge_lab.agents a
WHERE a.code IN ('HUNTER', 'QUANT', 'ARCHITECT', 'EXPLORER', 'SIMULATOR', 'CONTRARIAN', 'EVOLVER', 'BAYESIAN', 'CAPITALIST', 'GRANDMASTER')
ON CONFLICT DO NOTHING;

-- Display summary
SELECT a.code, a.display_name, a.status, a.operational_level, ac.current_capital 
FROM edge_lab.agents a
JOIN edge_lab.agent_capital ac ON ac.agent_id = a.agent_id
WHERE a.code IN ('HUNTER', 'QUANT', 'ARCHITECT', 'EXPLORER', 'SIMULATOR', 'CONTRARIAN', 'EVOLVER', 'BAYESIAN', 'CAPITALIST', 'GRANDMASTER')
ORDER BY a.code;
