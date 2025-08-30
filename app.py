import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import Dash, dcc, html
from dash.dependencies import Input, Output
import serial
import threading
import time

# ============ SERIAL CONFIG ============
SERIAL_PORT = "/dev/tty.usbserial-0001"  # <-- change to your Arduino port
BAUD_RATE = 115200

# open serial connection
ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)

# global dataframe
df_global = pd.DataFrame()
lock = threading.Lock()

# ============ BACKGROUND THREAD TO READ SERIAL ============
def serial_reader():
    global df_global
    header = []
    while True:
        try:
            line = ser.readline().decode("utf-8").strip()
            if not line:
                continue

            # first header detection
            if line.startswith("id,"):
                header = line.split(",")
                continue

            if header and "," in line:
                parts = line.split(",")
                if len(parts) == len(header):
                    row = dict(zip(header, parts))
                    try:
                        # convert numeric fields safely
                        row = {k: pd.to_numeric(v, errors="ignore") for k, v in row.items()}
                        row["sensor_key"] = str(row["id"]) + "_S" + str(row["index"])
                        with lock:
                            df_global = pd.concat([df_global, pd.DataFrame([row])], ignore_index=True)
                    except Exception as e:
                        print("Parse error:", e)

        except Exception as e:
            print("Serial error:", e)
            time.sleep(1)

# start background reader
threading.Thread(target=serial_reader, daemon=True).start()

# ============ PLOTTING HELPERS ============
def gas_ticks(ymin, ymax, n=6):
    ticks = np.linspace(ymin, ymax, n)
    ticktext = [f"{int(t):,} Ω\n({t:.0e})" for t in ticks]
    return ticks, ticktext

def make_figure(df, selected_sensor):
    sensors = df["sensor_key"].unique()
    if selected_sensor not in sensors:
        return go.Figure(), sensors

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

# ============ DASH APP ============
app = Dash(__name__)

# initial figure (empty until serial provides data)
df_init = pd.DataFrame(columns=["id","index","millis","temperature","pressure","humidity","gas_resistance","status","sensor_key"])
fig_init = go.Figure()

app.layout = html.Div([
    html.H2("BME688 Live Dashboard", style={"color":"white", "textAlign":"center"}),
    dcc.Dropdown(
        id="sensor-dropdown",
        options=[],  # will populate dynamically
        value=None,
        style={"width":"400px", "margin":"auto"}
    ),
    dcc.Graph(id="live-graph", figure=fig_init),
    dcc.Interval(
        id="interval-refresh",
        interval=2000,  # every 2 seconds
        n_intervals=0
    )
], style={"backgroundColor":"#111", "padding":"20px"})

@app.callback(
    [Output("live-graph", "figure"),
     Output("sensor-dropdown", "options"),
     Output("sensor-dropdown", "value")],
    Input("interval-refresh", "n_intervals"),
    Input("sensor-dropdown", "value")
)
def update_graph(n, selected_sensor):
    global df_global
    with lock:
        df = df_global.copy()

    if df.empty:
        return go.Figure(), [], None

    sensors = df["sensor_key"].unique()
    if not selected_sensor or selected_sensor not in sensors:
        selected_sensor = sensors[0]

    fig, sensors = make_figure(df, selected_sensor)
    return fig, [{"label": s, "value": s} for s in sensors], selected_sensor

if __name__ == "__main__":
    app.run(debug=True)
