import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

filename = "hp-test.csv"

# find first real header line
with open(filename, "r") as f:
    for i, line in enumerate(f):
        if line.startswith("id,"):
            header_line = i
            break

# read CSV starting at header, skip malformed rows automatically
df = pd.read_csv(
    filename,
    skiprows=header_line,       # jump directly to header
    on_bad_lines="skip"         # drop lines with wrong number of columns
)

# Create unique sensor key (ID + INDEX for classification)
    
df["sensor_key"] = df["id"].astype(str) + "_S" + df["index"].astype(str)
sensors = df["sensor_key"].unique()

# Function to generate Gas Resistance ticks with both numeric + scientific notation
def gas_ticks(ymin, ymax, n=6):
    ticks = np.linspace(ymin, ymax, n)
    ticktext = [f"{int(t):,} Ω\n({t:.0e})" for t in ticks]  # newline for readability
    return ticks, ticktext

# Global min/max for Gas Resistance for axis scale
global_min = df["gas_resistance"].min()
global_max = df["gas_resistance"].max()
global_ticks, global_ticktext = gas_ticks(global_min, global_max)

# Subplots layout (Gas bigger)
fig = make_subplots(
    rows=4, cols=2,  # ⬅️ now 4 rows
    specs=[[{"type":"scatter"}, {"type":"table"}],
           [{"type":"scatter"}, {"type":"table"}],
           [{"type":"scatter"}, None],
           [{"type":"scatter"}, None]],  # ⬅️ humidity here
    column_widths=[0.65, 0.35],
    row_heights=[0.50, 0.17, 0.17, 0.16],  # ⬅️ adjusted proportions
    shared_xaxes=True,
    vertical_spacing=0.05
)

sensor_traces = {}

for i, sensor in enumerate(sensors):
    d = df[df["sensor_key"]==sensor].sort_values("millis")
    traces = []

    # Gas Resistance plot
    gas_trace = go.Scatter(
        x=d["millis"], y=d["gas_resistance"],
        mode="lines+markers",
        name="Gas Resistance",
        hovertemplate="Gas: %{y:,.0f} Ω (%{y:.0e})<extra></extra>",
        visible=(i==0)
    )
    fig.add_trace(gas_trace, row=1, col=1)
    traces.append(gas_trace)

    # Temperature plot
    temp_trace = go.Scatter(
        x=d["millis"], y=d["temperature"],
        mode="lines+markers",
        name="Temperature (°C)",
        hovertemplate="%{y:.2f} °C<extra></extra>",
        visible=(i==0)
    )
    fig.add_trace(temp_trace, row=2, col=1)
    traces.append(temp_trace)

    # Pressure plot
    pres_trace = go.Scatter(
        x=d["millis"], y=d["pressure"],
        mode="lines+markers",
        name="Pressure (Pa)",
        hovertemplate="%{y:.2f} Pa<extra></extra>",
        visible=(i==0)
    )
    fig.add_trace(pres_trace, row=3, col=1)
    traces.append(pres_trace)

    # ✅ Humidity plot
    hum_trace = go.Scatter(
        x=d["millis"], y=d["humidity"],
        mode="lines+markers",
        name="Humidity (%)",
        hovertemplate="%{y:.2f}%<extra></extra>",
        visible=(i==0)
    )
    fig.add_trace(hum_trace, row=4, col=1)
    traces.append(hum_trace)

    # Raw data table
    table_cols = ["id","index","gas_resistance","status"]
    present_cols = [c for c in table_cols if c in d.columns]
    table_trace = go.Table(
        header=dict(values=[f"<b>{c}</b>" for c in present_cols],
                    fill_color="#111", font=dict(color="white")),
        cells=dict(values=[d[c] for c in present_cols],
                   fill_color="#1f2937", font=dict(color="white")),
        visible=(i==0),
        columnwidth=[1]*len(present_cols)
    )
    fig.add_trace(table_trace, row=1, col=2)
    traces.append(table_trace)

    # Stats table (MIN/MAX/AVG)
    stats_trace = go.Table(
        header=dict(values=["MIN","MAX","AVG"], fill_color="#111", font=dict(color="white")),
        cells=dict(values=[
            [f"{d['gas_resistance'].min():,.2f}"],
            [f"{d['gas_resistance'].max():,.2f}"],
            [f"{d['gas_resistance'].mean():,.2f}"]
        ],
        fill_color="#222222", font=dict(color="white")),
        visible=(i==0)
    )
    fig.add_trace(stats_trace, row=2, col=2)
    traces.append(stats_trace)

    sensor_traces[sensor] = traces

# Dropdown for sensor selection
buttons = []
for sensor in sensors:
    visible = []
    for s, traces in sensor_traces.items():
        for _ in traces:
            visible.append(s==sensor)
    buttons.append(dict(
        label=sensor,
        method="update",
        args=[{"visible": visible},
              {"title": f"BME688 Dashboard - {sensor}"}]
    ))

# Layout
fig.update_layout(
    template="plotly_dark",
    title=f"BME688 Dashboard - {sensors[0]}",
    updatemenus=[dict(
        active=0,
        buttons=buttons,
        x=0, y=1.12,
        direction="down",
        showactive=True,
        bgcolor="#333",
        bordercolor="#555"
    )],
    hovermode="x unified",
    height=1150, width=1500  # ⬅️ increased height for new row
)

# Axes titles and ticks
fig.update_yaxes(title_text="Gas Resistance (Ω)", row=1, col=1,
                 tickvals=global_ticks, ticktext=global_ticktext)
fig.update_yaxes(title_text="Temperature (°C)", row=2, col=1)
fig.update_yaxes(title_text="Pressure (Pa)", row=3, col=1)
fig.update_yaxes(title_text="Humidity (%)", row=4, col=1)

# Rangeslider on last x-axis
fig.update_xaxes(title_text="Time (ms)", row=4, col=1,
                 rangeslider_visible=True, rangeslider_thickness=0.10,)

# Show dashboard
fig.show()
