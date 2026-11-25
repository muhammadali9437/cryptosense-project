# CryptoSense AI: Documentation Package

| Folder | Contents |
|---|---|
| `documentation/` | **Main FYP documentation (updated edition)** in LaTeX, same structure as the previous University of Kotli documentation, with a "Changes Since the Previous Version" section (added / removed / changed) |
| `report/` | Project report: **`CryptoSense_AI_Project_Report_v2.pdf`** (ready to print, 25 pages, academic format) and the LaTeX source `report.tex` |
| `presentation/` | Slide deck: `CryptoSense_AI_Presentation_v2.pptx` (28 slides incl. diagrams and flowchart, university logo on every slide, presenter footer, fade animations, speaker notes) |
| `diagrams/` | 14 draw.io diagrams (`.drawio`) and `generate_diagrams.py` that produced them |
| `thesis/` | Alternative long-form edition in the COMSATS sample format (6 chapters); keep only if needed |

## 1. Compile the documentation (Overleaf)
1. Zip the `documentation` folder and upload it to Overleaf (New Project → Upload Project).
2. Menu → Compiler: **pdfLaTeX**. Main document: `main.tex`.
3. Recompile twice so the table of contents and the lists of figures and tables fill in.

Names, supervisor, co-supervisor, department, degree, session and month are macros at the top of
`documentation/main.tex` (block "project details"). The university logo is `documentation/figures/university_logo.png`.

## 2. Regenerate the appendix after code changes
Appendix A (routes), B (Python catalog) and C (Dart catalog) are generated from the source code:

```
python docs/documentation/tools/inventory.py . inventory.json
python docs/documentation/tools/gen_appendix.py inventory.json docs/documentation/generated
```
(run from the project root)

## 3. Diagrams (draw.io)
Open any `.drawio` file at https://app.diagrams.net (File → Open From → Device) or in draw.io Desktop.
They are fully editable. After editing, export (File → Export as → PNG, 200% zoom, white background)
with the same file name into `documentation/figures/diagrams/` (and `thesis/figures/diagrams/`).

| File | Diagram |
|---|---|
| 01_system_architecture | Layered system architecture |
| 02_use_case_diagram | Use cases |
| 03_activity_diagram | Main application flow |
| 04_class_diagram | Classes and relationships |
| 05_seq_authentication | Registration, login, authenticated request |
| 06_seq_signal_risk | AI signal and risk score |
| 07_seq_chat | Risk Copilot chat with six specialists |
| 08_seq_liquidation | Liquidation intelligence and alerts |
| 09_state_diagrams | Stream connection, alert lifecycle, signal availability |
| 10_er_diagram | Database entity relationship diagram |
| 11_ml_pipeline | Machine learning training pipeline |
| 12_deployment_diagram | Deployment |
| 13_signal_flowchart | Signal generation (unavailable instead of demo data) |
| 14_paper_trading_activity | Paper-trading activity |

## 4. Where the numbers come from
- 65/65 backend tests: `cd backend && venv\Scripts\python -m unittest discover -s tests` (re-run on 24 Nov 2026)
- Deployed model metrics: `backend/ml/models/metrics.json` (also `GET /api/signals/model-info`)
- 2/5/10-year comparison and the calibration/downside experiment: run on 24 Nov 2026.
  If you retrain or replace the models, update those tables.
