import pandas as pd
import numpy as np
import sqlalchemy as sa
from matplotlib import pyplot as plt
import seaborn as sns
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans, DBSCAN
from sklearn.metrics import silhouette_score
from sklearn.neighbors import NearestNeighbors
import os
import subprocess
import platform
from pathlib import Path


# Ensure folders exist
os.makedirs("plots/eda", exist_ok=True)
os.makedirs("plots/pca", exist_ok=True)
os.makedirs("plots/clustering", exist_ok=True)
os.makedirs("plots/dbscan", exist_ok=True)

# === CONFIGURATION ===
RUN_SCHEMA = False  # change to True for a schema.png
SQL_QUERY_PATH = "./sql/sessions.sql"  # Main SQL pipeline file
ENGINE_URL = (
    "postgresql+psycopg2://Test:bQNxVzJL4g6u@ep-noisy-flower-846766.us-east-2.aws.neon.tech:"
    "5432/TravelTide?sslmode=require&options=endpoint%3Dep-noisy-flower-846766"
)

# === PLOT DISPLAY MODE ===
SHOW_PLOTS = True  # Set to False when running unattended (e.g. batch run)

# === Generate Schema Diagram ===
def generate_schema_diagram():
    """Generates schema.dot and schema.png using eralchemy and Graphviz."""
    subprocess.run(["eralchemy", "-i", ENGINE_URL, "-o", "docs/schema.dot"])
    subprocess.run(["dot", "-Tpng", "docs/schema.dot", "-o", "docs/schema.png"])

def open_schema_image():
    """Opens schema.png in the default viewer (Preview on macOS)."""
    image_path = Path("docs/schema.png")
    if image_path.exists():
        if platform.system() == "Darwin":  # macOS
            subprocess.run(["open", str(image_path)])
        elif platform.system() == "Windows":
            os.startfile(image_path)
        else:
            subprocess.run(["xdg-open", str(image_path)])

# === UTILITY FUNCTIONS ===

def describe_nulls(df):
    """Print and return columns with more than 5% missing values."""
    null_pct = (df.isnull().sum() / len(df)) * 100
    print("\n🔍 Percentage of nulls per column:\n", null_pct)
    return null_pct[null_pct > 5].index.tolist()

def impute_missing(df, high_null_cols):
    """Fill missing values with median for numeric or 'Unknown' for categorical."""
    for col in high_null_cols:
        if pd.api.types.is_numeric_dtype(df[col]):
            median_val = df[col].median()
            df[col].fillna(median_val, inplace=True)
            print(f"🛠️ Imputed '{col}' with median: {median_val}")
        else:
            df[col].fillna("Unknown", inplace=True)
            print(f"🛠️ Imputed '{col}' with 'Unknown'")
    return df


def visualize_boxplot(df, column, title=None, save_path=None):
    """Plot boxplot of a column, save it, and optionally show it."""
    plt.figure(figsize=(8, 4))
    plt.boxplot(df[column].dropna(), vert=False)
    plt.xlabel(column)
    plt.title(title or f"Boxplot of {column}")
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path)
        print(f"💾 Saved plot to {save_path}")
    if SHOW_PLOTS:
        plt.show()
    else:
        plt.close()

def visualize_histogram(df, column, bins=10, xlim=None, title=None, save_path=None):
    """Plot histogram of a column, save it, and optionally show it."""
    plt.figure(figsize=(10, 6))
    plt.hist(df[column].dropna(), bins=bins, color='skyblue', edgecolor='black')
    plt.xlabel(column)
    plt.ylabel("Frequency")
    if xlim:
        plt.xlim(xlim)
    plt.title(title or f"Histogram of {column}")
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path)
        print(f"💾 Saved plot to {save_path}")
    if SHOW_PLOTS:
        plt.show()
    else:
        plt.close()

# === MAIN PIPELINE ===

def main():
    # --- Step 1: Load SQL Query ---
    try:
        with open(SQL_QUERY_PATH, "r") as f:
            query = f.read()
    except FileNotFoundError:
        print(f"❌ SQL file not found at: {SQL_QUERY_PATH}")
        return  # exit the `main()` function


    # --- Step 2: Prepare output folders ---
    os.makedirs("clusters", exist_ok=True)
    os.makedirs("perks", exist_ok=True)

    # --- Step 3: Load session-based user data ---
    try:
        engine = sa.create_engine(ENGINE_URL)
        with engine.connect() as conn:
            final_df = pd.read_sql(sa.text(query), conn)
    except Exception as e:
        print("❌ Failed to connect to the database or run the query.")
        print("Error details:", e)
        return

    # --- Step 4: Enrich with hotel stay duration ---
    hotel_query = """
                  WITH sessions_2023 AS (SELECT * \
                                         FROM sessions \
                                         WHERE session_start > '2023-01-04'),
                       filtered_users AS (SELECT user_id \
                                          FROM sessions_2023 \
                                          GROUP BY user_id \
                                          HAVING COUNT(*) > 7),
                       session_base AS (SELECT s.user_id, s.trip_id, h.check_in_time, h.check_out_time \
                                        FROM sessions_2023 s \
                                                 LEFT JOIN hotels h ON s.trip_id = h.trip_id \
                                        WHERE s.user_id IN (SELECT user_id FROM filtered_users)),
                       canceled_trips AS (SELECT DISTINCT trip_id \
                                          FROM session_base \
                                          WHERE trip_id IS NOT NULL \
                                            AND check_in_time IS NULL),
                       not_canceled_trips AS (SELECT * \
                                              FROM session_base \
                                              WHERE trip_id IS NOT NULL \
                                                AND trip_id NOT IN (SELECT trip_id FROM canceled_trips))
                  SELECT * \
                  FROM not_canceled_trips
                  WHERE check_in_time IS NOT NULL \
                    AND check_out_time IS NOT NULL; \
                  """

    with engine.connect() as conn:
        hotel_df = pd.read_sql(sa.text(hotel_query), conn)

    hotel_df["check_in_time"] = pd.to_datetime(hotel_df["check_in_time"])
    hotel_df["check_out_time"] = pd.to_datetime(hotel_df["check_out_time"])
    hotel_df["total_nights"] = (hotel_df["check_out_time"] - hotel_df["check_in_time"]).dt.days

    avg_nights_df = hotel_df.groupby("user_id")["total_nights"].mean().reset_index()
    avg_nights_df.rename(columns={"total_nights": "avg_nights_per_trip"}, inplace=True)

    final_df = final_df.merge(avg_nights_df, on="user_id", how="left")
    final_df["avg_nights_per_trip"] = final_df["avg_nights_per_trip"].fillna(0)

    # --- Step 5: Data cleaning ---
    high_nulls = describe_nulls(final_df)
    final_df = impute_missing(final_df, high_nulls)

    # Drop unnecessary columns
    drop_cols = ['departure_time', 'return_time', 'check_in_time', 'check_out_time', 'home_airport', 'home_city']
    final_df.drop(columns=[col for col in drop_cols if col in final_df.columns], inplace=True)

    # Encode categorical features
    final_df["gender"] = (final_df["gender"] == 'F').astype(int)
    final_df["home_country"] = (final_df["home_country"] == 'canada').astype(int)
    final_df["married"] = final_df["married"].astype(int)
    final_df["has_children"] = final_df["has_children"].astype(int)

    # --- Step 6: EDA: Histograms & Boxplots ---
    visualize_histogram(
        final_df,
        column='num_clicks',
        bins=100,
        xlim=(0, 100),
        title='Clicks',
        save_path='plots/eda/clicks_histogram.png'
    )

    visualize_boxplot(
        final_df,
        column='num_clicks',
        title='Boxplot of Clicks',
        save_path='plots/eda/clicks_boxplot.png'
    )
    visualize_histogram(
        final_df,
        column='age',
        bins=10,
        xlim=(0, 100),
        title='Histogram of Age',
        save_path='plots/eda/age_histogram.png'
    )

    # --- Step 7: PCA + KMeans Clustering ---
    numeric_df = final_df.select_dtypes(include='number')
    scaled_df = pd.DataFrame(StandardScaler().fit_transform(numeric_df), columns=numeric_df.columns)

    pca = PCA(n_components=12)
    data_after_pca = pd.DataFrame(pca.fit_transform(scaled_df), columns=[f"pca_{i}" for i in range(12)])

    # Visualize explained variance
    plt.figure(figsize=(8, 6))
    plt.plot(np.cumsum(pca.explained_variance_ratio_), marker='o', linestyle='--')
    plt.axhline(y=0.95, color='red', linestyle='--')
    plt.title('Explained Variance by PCA Components')
    plt.xlabel('Number of Components')
    plt.ylabel('Cumulative Explained Variance')
    plt.tight_layout()
    plt.savefig("plots/pca/pca_explained_variance.png")
    print("💾 Saved: plots/pca/pca_explained_variance.png")
    plt.show()

    # PCA loadings heatmap
    plt.figure(figsize=(10, 8))
    sns.heatmap(
        np.abs(pd.DataFrame(pca.components_, columns=scaled_df.columns).T),
        cmap='viridis'
    )
    plt.title("PCA Component Weights (abs)")
    plt.tight_layout()
    plt.savefig("plots/pca/pca_loadings_heatmap.png")
    print("💾 Saved: plots/pca/pca_loadings_heatmap.png")
    plt.show()

    # Evaluate silhouette scores for multiple cluster counts
    scores = []
    for n_clusters in range(2, 20):
        kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        groups = kmeans.fit_predict(data_after_pca)
        score = silhouette_score(data_after_pca, groups)
        scores.append(score)
        print(f"Silhouette score for {n_clusters} clusters: {score:.4f}")

    # Plot silhouette scores
    plt.figure(figsize=(10, 6))
    sns.lineplot(x=range(2, 20), y=scores)
    plt.title("Silhouette Scores by Cluster Count")
    plt.xlabel("Number of Clusters")
    plt.ylabel("Silhouette Score")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig("plots/clustering/silhouette_scores.png")
    print("💾 Saved: plots/clustering/silhouette_scores.png")
    plt.show()

    # Final clustering
    kmeans = KMeans(n_clusters=9, random_state=42)
    final_df["group_k_means"] = kmeans.fit_predict(data_after_pca)

    # Map cluster IDs to human-readable names
    cluster_labels = {
        0: "Luxury Loyalists",
        1: "Young Adventurers",
        2: "Family Vacationers",
        3: "Weekend Explorers",
        4: "Budget Travelers",
        5: "Spontaneous Bookers",
        6: "Frequent Flyers",
        7: "Solo Jetsetters",
        8: "Last-Minute Planners"
    }

    # Add column with cluster names to the final DataFrame
    final_df["cluster_name"] = final_df["group_k_means"].map(cluster_labels)
    #add value_score
    final_df["value_score"] = (
            final_df["money_spent_hotel"] / (final_df["num_sessions"] + 1)
    )

    # STEP 2: Summarize cluster behaviors
    cluster_summary = final_df.groupby("cluster_name").agg({
        "age": "mean",
        "money_spent_hotel": "mean",
        "num_sessions": "mean",
        "num_trips": "mean",
        "value_score": "mean",
        "has_children": "mean",
        "avg_bags": "mean",
        "avg_nights_per_trip": "mean"
    }).round(2)

    cluster_summary = cluster_summary.rename(columns={"converted": "conversion_rate"})

    # Preview summary in terminal
    print("\n📊 Cluster Behavior Summary:")
    print(cluster_summary)

    # export for Tableau or slides
    cluster_summary.to_csv("cluster_summary.csv")

    print("\n📊 Mean values per cluster:")
    print(final_df.groupby("group_k_means").mean(numeric_only=True))

    print("\n🎁 Cluster vs Perk:")
    print(pd.crosstab(final_df["group_k_means"], final_df["perk"]))

    # --- Step 8: Booking Segment Assignment ---
    def assign_booking_segment(row):
        if row["num_trips"] == 0:
            return "First Timer"
        elif row["num_flights"] >= 10 and row["avg_km_flown"] > 5000:
            return "Frequent Flyer"
        elif row["money_spent_hotel"] >= 1500 and row["avg_nights_per_trip"] >= 5:
            return "Luxury Traveler"
        elif row["time_after_booking"] >= 10:
            return "Planner"
        elif row["time_after_booking"] < 3:
            return "Spontaneous Booker"
        elif row["has_children"] == 1 and row["avg_bags"] > 2:
            return "Family Traveler"
        elif row["num_sessions"] < 5 or row["num_clicks"] < 10:
            return "Low Engagement"
        else:
            return "General"

    final_df["booking_segment"] = final_df.apply(assign_booking_segment, axis=1)

    # --- Step 9: Value Score Calculation ---
    score_features = ["money_spent_hotel", "num_trips", "avg_session_duration", "num_clicks"]
    normalized = MinMaxScaler().fit_transform(final_df[score_features])
    final_df["value_score"] = (
        normalized[:, 0] * 0.4 +  # hotel spending
        normalized[:, 1] * 0.3 +  # number of trips
        normalized[:, 2] * 0.2 +  # session duration
        normalized[:, 3] * 0.1    # clicks
    ) * 100

    # --- Step 10: Cross-tabulations ---
    print("\n📊 Cluster vs Gender:")
    print(pd.crosstab(final_df["group_k_means"], final_df["gender"]))

    print("\n📊 Cluster vs Gender + Children:")
    print(pd.crosstab(final_df["group_k_means"], [final_df["gender"], final_df["has_children"]]))

    print("\n📊 Cluster vs Gender + Children + Country:")
    print(pd.crosstab(final_df["group_k_means"], [final_df["gender"], final_df["has_children"], final_df["home_country"]]))

    # --- Step 11: DBSCAN Density Clustering (for validation) ---
    neighbors = NearestNeighbors(n_neighbors=5)
    distances, _ = neighbors.fit(data_after_pca).kneighbors(data_after_pca)
    distances = np.sort(distances[:, 4])
    plt.figure(figsize=(10, 6))
    plt.plot(distances)
    plt.title("k-Distance Graph (DBSCAN)")
    plt.xlabel("Points sorted by distance")
    plt.ylabel("Distance to 5th Nearest Neighbor")
    plt.tight_layout()
    plt.savefig("plots/dbscan/dbscan_k_distance.png")
    print("💾 Saved: plots/dbscan/dbscan_k_distance.png")
    plt.show()

    dbscan = DBSCAN(eps=0.4, min_samples=4)
    final_df["group_dbscan"] = dbscan.fit_predict(data_after_pca)

    # --- Step 12: Save Segment/Cluster Files ---
    for group_id in final_df["group_k_means"].unique():
        group_df = final_df[final_df["group_k_means"] == group_id]
        group_df.to_csv(f"clusters/cluster_{group_id}.csv", index=False)
        print(f"💾 Saved: clusters/cluster_{group_id}.csv")

    for perk_name, group_df in final_df.groupby("perk"):
        safe_name = perk_name.replace(" ", "_").replace("%", "percent")
        group_df.to_csv(f"perks/perk_{safe_name}.csv", index=False)
        print(f"💾 Saved: perks/perk_{safe_name}.csv")

    # Final dataset saves
    final_df.to_csv("cleaned_sessions.csv", index=False)
    data_after_pca.to_csv("pca_sessions.csv", index=False)
    final_df.to_csv("final_with_segments_and_score.csv", index=False)
    print("\n💾 Saved: cleaned_sessions.csv, pca_sessions.csv, and final_with_segments_and_score.csv")

# === RUN MAIN ===
if __name__ == "__main__":
    main()

    if RUN_SCHEMA:
        try:
            generate_schema_diagram()
            open_schema_image()
        except Exception as e:
            print(f"⚠️ Schema diagram failed: {e}")