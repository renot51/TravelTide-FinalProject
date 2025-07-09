import os
import shutil

# === Configuration ===
keep_files = {
    "TravelTide Final-Project Ehud.py",
    "cleaned_sessions.csv",
    "pca_sessions.csv",
    "sql",
    "clusters",
    "final_with_segments_and_score.csv",
}

# === Create folders ===
os.makedirs("docs", exist_ok=True)
os.makedirs("exports", exist_ok=True)

# === Move documentation-related files ===
for file in os.listdir("."):
    if file.endswith((".docx", ".pptx", ".png", ".dot", ".md")):
        print(f"📁 Moving {file} to docs/")
        shutil.move(file, os.path.join("docs", file))

# === Move exports (.csv) ===
for file in os.listdir("."):
    if file.endswith(".csv") and file not in keep_files:
        print(f"📁 Moving {file} to exports/")
        shutil.move(file, os.path.join("exports", file))

# === Delete old/unused scripts ===
old_scripts = ["analysis1.py"]
for file in old_scripts:
    if os.path.exists(file):
        print(f"🗑️ Deleting {file}")
        os.remove(file)

# === Summary ===
print("\n✅ Cleanup complete. Organized files into:")
print(" - docs/ for documentation and diagrams")
print(" - exports/ for CSV outputs")
print(" - main directory for current scripts and clusters")
