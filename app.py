import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import Dash, dcc, html
from dash.dependencies import Input, Output

# Path to your CSV file
FILENAME = "/Users/tallesrocha/Desktop/sempreiot-new/code/bme688-api-sensor/hp-test.csv"

# Helper function to load + process CSV
def load_data():
    # find first real header line
    with open(FILENAME, "r") as f:
        for i, line in enumerate(f):
            if line.startswith("id,"):
                header_line = i
                break

    # read CSV starting at header, skip malformed rows automatically
    df = pd.read_csv(
        FILENAME,
        skiprows=header_line,
        on_bad_lines="skip"
    )

    if "status" in df.columns:
        df = df[df["status"].astype(str) != "a0"]
    # Create unique sensor key (ID + INDEX for classification)
    df["sensor_key"] = df["id"].astype(str) + "_S" + df["index"].astype(str)
    return df

# Function to generate Gas Resistance ticks with both numeric + scientific notation
def gas_ticks(ymin, ymax, n=6):
    ticks = np.linspace(ymin, ymax, n)
    ticktext = [f"{int(t):,} Ω\n({t:.0e})" for t in ticks]
    return ticks, ticktext

# Build figure given a dataframe
def make_figure(df, selected_sensor):
    sensors = df["sensor_key"].unique()
    d = df[df["sensor_key"] == selected_sensor].sort_values("millis")

    # Global min/max for Gas Resistance for axis scale
    global_min = df["gas_resistance"].min()
    global_max = df["gas_resistance"].max()
    global_ticks, global_ticktext = gas_ticks(global_min, global_max)

    fig = make_subplots(
        rows=4, cols=2,
        specs=[[{"type":"scatter"}, {"type":"table"}],
               [{"type":"scatter"}, {"type":"table"}],
               [{"type":"scatter"}, None],
               [{"type":"scatter"}, None]],
        column_widths=[0.65, 0.35],
        row_heights=[0.50, 0.17, 0.17, 0.16],
        shared_xaxes=True,
        vertical_spacing=0.05
    )

    # Gas Resistance
    fig.add_trace(go.Scatter(
        x=d["millis"], y=d["gas_resistance"],
        mode="lines+markers",
        name="Gas Resistance",
        hovertemplate="Gas: %{y:,.0f} Ω (%{y:.0e})<extra></extra>"
    ), row=1, col=1)

    # Temperature
    fig.add_trace(go.Scatter(
        x=d["millis"], y=d["temperature"],
        mode="lines+markers",
        name="Temperature (°C)",
        hovertemplate="%{y:.2f} °C<extra></extra>"
    ), row=2, col=1)

    # Pressure
    fig.add_trace(go.Scatter(
        x=d["millis"], y=d["pressure"],
        mode="lines+markers",
        name="Pressure (Pa)",
        hovertemplate="%{y:.2f} Pa<extra></extra>"
    ), row=3, col=1)

    # Humidity
    fig.add_trace(go.Scatter(
        x=d["millis"], y=d["humidity"],
        mode="lines+markers",
        name="Humidity (%)",
        hovertemplate="%{y:.2f}%<extra></extra>"
    ), row=4, col=1)

    # Raw data table
    table_cols = ["id", "index", "gas_resistance", "status"]
    present_cols = [c for c in table_cols if c in d.columns]
    fig.add_trace(go.Table(
        header=dict(values=[f"<b>{c}</b>" for c in present_cols],
                    fill_color="#111", font=dict(color="white")),
        cells=dict(values=[d[c] for c in present_cols],
                   fill_color="#1f2937", font=dict(color="white")),
    ), row=1, col=2)

    # Stats table
    fig.add_trace(go.Table(
        header=dict(values=["MIN", "MAX", "AVG"], fill_color="#111", font=dict(color="white")),
        cells=dict(values=[
            [f"{d['gas_resistance'].min():,.2f}"],
            [f"{d['gas_resistance'].max():,.2f}"],
            [f"{d['gas_resistance'].mean():,.2f}"]
        ],
        fill_color="#222222", font=dict(color="white"))
    ), row=2, col=2)

    # Layout
    fig.update_layout(
        template="plotly_dark",
        title=f"BME688 Dashboard - {selected_sensor}",
        hovermode="x unified",
        height=1150, width=1500
    )

    # Axes titles
    fig.update_yaxes(title_text="Gas Resistance (Ω)", row=1, col=1,
                     tickvals=global_ticks, ticktext=global_ticktext)
    fig.update_yaxes(title_text="Temperature (°C)", row=2, col=1)
    fig.update_yaxes(title_text="Pressure (Pa)", row=3, col=1)
    fig.update_yaxes(title_text="Humidity (%)", row=4, col=1)

    fig.update_xaxes(title_text="Time (ms)", row=4, col=1,
                     rangeslider_visible=True, rangeslider_thickness=0.10)

    return fig, sensors

# ------------------- DASH APP -------------------
app = Dash(__name__)

df_init = load_data()
sensors_init = df_init["sensor_key"].unique()  # define sensors first
fig_init, _ = make_figure(df_init, sensors_init[0])  # build figure with first sensor

app.layout = html.Div([
    html.H2("BME688 Live Dashboard", style={"color":"white", "textAlign":"center"}),
    dcc.Dropdown(
        id="sensor-dropdown",
        options=[{"label": s, "value": s} for s in sensors_init],
        value=sensors_init[0],
        style={"width":"400px", "margin":"auto"}
    ),
    dcc.Graph(id="live-graph", figure=fig_init),
    dcc.Interval(
        id="interval-refresh",
        interval=1*60*1000,  # 5 minutes
        n_intervals=0
    )
], style={"backgroundColor":"#111", "padding":"20px"})

@app.callback(
    Output("live-graph", "figure"),
    Input("interval-refresh", "n_intervals"),
    Input("sensor-dropdown", "value")
)
def update_graph(n, selected_sensor):
    df = load_data()
    fig, _ = make_figure(df, selected_sensor)
    return fig

if __name__ == "__main__":
    app.run(debug=True)
