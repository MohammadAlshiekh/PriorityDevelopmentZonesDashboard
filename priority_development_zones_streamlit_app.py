import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import shapely
import numpy as np

st.set_page_config(page_title="Priority Development Zones", layout="wide")

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # Loading Data # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 

# Load the feather file quietly
feather_path = "parcels_current_land_use.feather"
try:
    gdf = gpd.read_feather(feather_path)
except Exception as e:
    st.error(f"Failed to load Feather file: {e}")
    st.stop()

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # Filteration # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 

# Unique sorted filter values
sub_municipality_options = sorted(gdf['ID_SUB_MUNICIPALITY'].dropna().unique())
hay_options = sorted(gdf['ID_HAY'].dropna().unique())

# st.sidebar.title("🧭 Configuration Panel")

st.sidebar.markdown("### 📍 Location Filters")

filter_cols = st.sidebar.columns(2)
selected_sub = filter_cols[0].selectbox("🏘️ Sub-Municipality", sub_municipality_options, index=0)
selected_hay = filter_cols[1].selectbox("📌 District (HAY)", hay_options, index=hay_options.index(5))

st.sidebar.markdown("---")

zone_filter = st.sidebar.pills(
    "Select Zones to Display:",
    selection_mode = "multi",
    options=[0, 1, 2],
    default=[0, 1, 2],
    format_func=lambda x: f"Zone {x}",
)

show_only_empty = st.sidebar.toggle(
    "Only show empty developable parcels",
    value = True,
)

st.sidebar.markdown("---")

# Apply filter to main GeoDataFrame (input to calculations)
selected_district = gdf.loc[
    (gdf['ID_SUB_MUNICIPALITY'] == selected_sub) &
    (gdf['ID_HAY'] == selected_hay)
].copy()

if show_only_empty:
    filtered_parcels = selected_district.loc[
        (selected_district["DWELLING_U"] == 0) &
        (selected_district['FLOOR_ABOV'] == 0) &
        (selected_district['DESCRIPTIO'] == 'DEVELOPABLE SUBDIVIDED - WITH PAVED STREET')
    ].copy(deep=True)
else:
    filtered_parcels = selected_district.copy(deep=True)


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # Configuration # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 

# 📐 Unit Sizes
st.sidebar.markdown("### 📐 Average Unit Sizes (m²)")

unit_cols = st.sidebar.columns(3)
average_large_unit_size = unit_cols[0].number_input("🏢 Large", min_value=0, value=500, step=50)
average_medium_unit_size = unit_cols[1].number_input("🏘️ Medium", min_value=0, value=250, step=50)
average_small_unit_size = unit_cols[2].number_input("🏚️ Small", min_value=0, value=150, step=50)

# 💰 Land Price Inputs
st.sidebar.markdown("### 💰 Land Price (﷼/m²)")

zone_cols = st.sidebar.columns(3)
zone0_price = zone_cols[0].number_input("🟥 Zone 0", min_value=0, value=25000, step=1000)
zone1_price = zone_cols[1].number_input("🟧 Zone 1", min_value=0, value=10000, step=1000)
zone2_price = zone_cols[2].number_input("🟩 Zone 2", min_value=0, value=6000, step=500)

average_land_price = np.array([zone0_price, zone1_price, zone2_price])

# 🧱 Construction Cost
st.sidebar.markdown("### 🧱 GFA Construction Cost")

average_GFA_construction_cost = st.sidebar.number_input(
    "🧾 Avg. Cost per m² (﷼)", min_value=0, value=2000, step=100
)

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # Assigning Zones # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 

z0 = [(1, 103), (1, 106), (2, 128), (2, 138)]
z1 = [
        (2, 104), (2, 105), (2, 113), (2, 152),
        (3, 103), (3, 162), (3, 180),
        (4, 101), (4, 103), (5, 105)
    ]

filtered_parcels['sub_hay_block'] = filtered_parcels.apply(lambda row: (row['ID_SUB_HAY'], row['ID_BLOCK']), axis=1)

filtered_parcels['assigned_zone'] = filtered_parcels['sub_hay_block'].apply(lambda x: 0 if x in z0 else (1 if x in z1 else 2))

zone_colors = {0: "red", 1: "orange", 2: "green"}

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # Calculating GFA # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 

zoning_regulation = {
    'setback': [4, 3, 2], # 2 meter setback all around
    'max_cover': [.75, .75, .75], # maximum building footprint to parcel ratio
    'FAR': [6, 2.5, 1.2], 
    'max_floor' : [20, 4, 3],
    'last_floor_cover' : [1, .75, .50] # max last floor to preivous floor ratio
}

parcel_idxs = []
geometries = []
floor_counts = []
GFAs = []
last_floor_areas = []
zones = []
parcel_areas = []

for parcel_idx in filtered_parcels.index.values:
    #parcel_idx = filtered_parcels.index.values[filtered_parcels.area.argmax()]
    parcel_geom = filtered_parcels.at[parcel_idx, 'geometry']
    parcel_zone = filtered_parcels.at[parcel_idx, 'assigned_zone']
    offset_parcel = parcel_geom.buffer(-1*zoning_regulation['setback'][parcel_zone])

    footprint_cover_ratio = offset_parcel.area / parcel_geom.area
    max_cover_ratio = zoning_regulation['max_cover'][parcel_zone]
    if  footprint_cover_ratio > max_cover_ratio:
        scaled_parcel = shapely.affinity.scale(parcel_geom, max_cover_ratio, max_cover_ratio)
    else:
        scaled_parcel = offset_parcel 

        
    max_gfa = parcel_geom.area * zoning_regulation['FAR'][parcel_zone]
    floor_count = np.ceil(max_gfa / scaled_parcel.area)

    max_floors = zoning_regulation['max_floor'][parcel_zone]
    if floor_count > max_floors:
        floor_count = max_floors


    inner_floors_area = (floor_count - 1) * scaled_parcel.area
    last_floor_area = max_gfa - inner_floors_area
    last_floor_area_ratio = last_floor_area/scaled_parcel.area

    if last_floor_area_ratio > zoning_regulation['last_floor_cover'][parcel_zone]:

        last_floor_area = scaled_parcel.area * zoning_regulation['last_floor_cover'][parcel_zone]

    total_GFA = inner_floors_area + last_floor_area

    parcel_idxs.append(parcel_idx)
    geometries.append(scaled_parcel)
    floor_counts.append(floor_count)
    GFAs.append(total_GFA)
    last_floor_areas.append(last_floor_area)
    zones.append(parcel_zone)
    parcel_areas.append(parcel_geom.area)


new_buildings = gpd.GeoDataFrame(
    {
        'parcel_idx': parcel_idxs,
        'zone': zones,
        'parcel_area': parcel_areas,
        'floor_count': floor_counts,
        'GFA': GFAs,
        'last_floor_area': last_floor_areas,
        'geometry': geometries,
    },
    crs = filtered_parcels.crs
)


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # Unit Calculations # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 


new_buildings['small_unit_count'] = np.floor(new_buildings['GFA'] / average_small_unit_size)
new_buildings['medium_unit_count'] = np.floor(new_buildings['GFA'] / average_medium_unit_size)
new_buildings['large_unit_count'] = np.floor(new_buildings['GFA'] / average_large_unit_size)

new_buildings['land_price'] = new_buildings['parcel_area'] * average_land_price[new_buildings['zone']]

new_buildings['small_unit_cost'] = (
    new_buildings['small_unit_count'] * average_small_unit_size * average_GFA_construction_cost + new_buildings['land_price']
    ) / new_buildings['small_unit_count']

new_buildings['medium_unit_cost'] = (
    new_buildings['medium_unit_count'] * average_medium_unit_size * average_GFA_construction_cost + new_buildings['land_price']
    ) / new_buildings['medium_unit_count']

new_buildings['large_unit_cost'] = (
    new_buildings['large_unit_count'] * average_large_unit_size * average_GFA_construction_cost + new_buildings['land_price']
    ) / new_buildings['large_unit_count']

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # Plotting # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 

mapped_frame = new_buildings[new_buildings['zone'].isin(zone_filter)].copy()

# Reproject to EPSG:4326 if not already
if mapped_frame.crs != "EPSG:4326":
    mapped_frame = mapped_frame.to_crs(epsg=4326)

sar_icon = "<img src='https://www.sama.gov.sa/ar-sa/Currency/Documents/Saudi_Riyal_Symbol-2.svg' width='14' style='vertical-align: middle;'>"

st.markdown("### 📊 Summary Statistics")
col1, col2, col3 = st.columns(3)
col1.metric("Parcels", len(mapped_frame))
col2.metric("Total GFA", f"{mapped_frame['GFA'].sum():,.0f} m²")
col3.metric("Total Parcel Area", f"{mapped_frame['parcel_area'].sum():,.0f} m²")
col5, col6, col7 = st.columns(3)
# handle NaN or inf values in unit counts
col5.metric("Max Total Small Units", f"{mapped_frame['small_unit_count'].sum():,.0f}")
col6.metric("Max Total Medium Units", f"{mapped_frame['medium_unit_count'].sum():,.0f}")
col7.metric("Max Total Large Units", f"{mapped_frame['large_unit_count'].sum():,.0f}")
col8, col9, col10 = st.columns(3)
# drop inf or NaN values before calculating means
col8.metric(
    "Avg. Small Unit Cost", f"{mapped_frame['small_unit_cost'].replace([np.inf, -np.inf], np.nan).dropna().mean():,.0f} ﷼")
col9.metric(
    "Avg. Medium Unit Cost", f"{mapped_frame['medium_unit_cost'].replace([np.inf, -np.inf], np.nan).dropna().mean():,.0f} ﷼")
col10.metric(
    "Avg. Large Unit Cost", f"{mapped_frame['large_unit_cost'].replace([np.inf, -np.inf], np.nan).dropna().mean():,.0f} ﷼")

st.sidebar.caption("⚠️ The new SAR symbol isn’t in Unicode yet — using SAR/﷼ as a placeholder.")

st.header("🗺️ Interactive Map")

# Display
if not mapped_frame.empty:
    center = [
        mapped_frame.geometry.to_crs(epsg=4326).union_all().centroid.y,
        mapped_frame.geometry.to_crs(epsg=4326).union_all().centroid.x
    ]
    m = folium.Map(location=center, zoom_start=15)

    for _, row in mapped_frame.iterrows():
        tooltip_html = f"""Parcel ID: {row.get('parcel_idx', 'N/A')}<br>
                            Assigned Zone: {row['zone']}<br>
                            GFA: {row['GFA']:,.0f} m²<br>
                            Floor Count: {row['floor_count']:.0f}<br>
                            Last Floor Area: {row['last_floor_area']:,.0f} m²<br>
                            Parcel Area: {row['parcel_area']:,.0f} m²<br>
                            Small Units: {row['small_unit_count']:.0f}<br>
                            Medium Units: {row['medium_unit_count']:.0f}<br>
                            Large Units: {row['large_unit_count']:.0f}<br>
                            Small Unit Cost: {row['small_unit_cost']:,.0f} {sar_icon}<br>
                            Medium Unit Cost: {row['medium_unit_cost']:,.0f} {sar_icon}<br>
                            Large Unit Cost: {row['large_unit_cost']:,.0f} {sar_icon}<br>
                            Land Price: {row['land_price']:,.0f} {sar_icon}<br>
                            Total Cost: {row['small_unit_cost'] * row['small_unit_count']:,.0f} {sar_icon}<br>
                            """
        folium.GeoJson(
            row.geometry,
            tooltip=folium.Tooltip(tooltip_html),
            style_function=lambda feat, z=row['zone']: {
                'color': zone_colors.get(z, "gray"),
                'weight': 2,          # Line thickness (in pixels)
                'fillOpacity': 0.5      # Optional: make polygon slightly transparent
            }
        ).add_to(m)

    st_folium(m, width=1200, height=600)
else:
    st.warning("No parcels match the selected filters.")