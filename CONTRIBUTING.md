# 🤝 Guide de contribution — SolarDecide DZ

Merci de l'intérêt que vous portez à SolarDecide DZ ! Voici comment contribuer efficacement.

## 🚀 Démarrage rapide

1. **Fork** le dépôt sur GitHub
2. **Clone** votre fork localement
   ```bash
   git clone https://github.com/VOTRE-USERNAME/SolarDecide-DZ.git
   cd SolarDecide-DZ
   ```
3. **Créez une branche** pour votre fonctionnalité
   ```bash
   git checkout -b feature/ma-fonctionnalite
   # ou
   git checkout -b fix/mon-correctif
   ```
4. **Installez les dépendances**
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

## 📝 Conventions de commit

Nous utilisons les [Conventional Commits](https://www.conventionalcommits.org/) :

| Préfixe | Usage | Exemple |
|---|---|---|
| `feat:` | Nouvelle fonctionnalité | `feat: ajout du calcul d'IRR sur 30 ans` |
| `fix:` | Correction de bug | `fix: erreur 500 sur /api/forecast vide` |
| `docs:` | Documentation | `docs: ajout exemple cURL ROI` |
| `style:` | Formatage (sans logique) | `style: PEP-8 dans plan_service.py` |
| `refactor:` | Refactor sans changement fonctionnel | `refactor: extraction du helper _norm01` |
| `perf:` | Amélioration de performance | `perf: cache DuckDB sur /classement` |
| `test:` | Ajout / modification de tests | `test: couverture roi.py` |
| `chore:` | Maintenance / outillage | `chore: bump Flask 3.1.3 → 3.1.4` |

## 🎨 Style de code

### Python (backend)
- **PEP-8** strict, longueur de ligne ≤ 100 caractères
- **Type hints** pour toute nouvelle fonction publique
- **Docstrings** en français, format Google
- Pas de `print()` — utiliser le logger

### JavaScript (frontend)
- Vanilla ES6+ (pas de build step)
- 2 espaces d'indentation
- `const`/`let`, jamais `var`
- Fonctions fléchées préférées

## 🧪 Tests

Avant d'ouvrir une PR :

```bash
# Vérifier que l'app démarre
cd backend && python app.py

# Health check
curl http://localhost:5000/api/health

# Tester votre endpoint
curl http://localhost:5000/api/votre-route
```

## 📋 Checklist Pull Request

- [ ] Le code respecte le style du projet
- [ ] J'ai testé localement sur Ubuntu / macOS / Windows
- [ ] Pas de secrets / clés / mots de passe dans le code
- [ ] Le README est à jour (si endpoints/fonctionnalités modifiés)
- [ ] Le message de commit suit Conventional Commits

## 🐛 Signaler un bug

Ouvrez une [issue GitHub](https://github.com/VOTRE-USERNAME/SolarDecide-DZ/issues) en incluant :

- Description claire du problème
- Étapes pour reproduire
- Comportement attendu vs observé
- Capture d'écran / logs si pertinent
- Environnement (OS, version Python, navigateur)

## 💡 Proposer une fonctionnalité

Avant de coder une grosse feature, ouvrez une **discussion** pour en parler. Cela évite de travailler sur quelque chose qui ne serait pas mergé.

## 📜 Licence

En contribuant, vous acceptez que votre code soit publié sous la même licence MIT que le projet.

Merci ! 🌞
