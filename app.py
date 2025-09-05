import threading
import time
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import Dash, dcc, html
from dash.dependencies import Input, Output, State
import dash

# ------------ SERIAL CONFIG ------------
SERIAL_PORT = "/dev/cu.usbserial-0001"
BAUDRATE = 115200
SERIAL_TIMEOUT = 1.0
MAX_BUFFER_LINES = 200_000
# --------------------------------------

serial_lock = threading.Lock()
serial_header = None
serial_buffer = []

# ---------------- SERIAL WORKER ----------------
def serial_worker(port, baud, timeout):
    global serial_header, serial_buffer
    import serial
    while True:
        try:
            ser = serial.Serial(port, baud, timeout=timeout)
            print(f"[serial_reader] Opened {port} @ {baud}")
            while True:
                raw = ser.readline()
                if not raw:
                    continue
                try:
                    line = raw.decode("utf-8", errors="replace").strip()
                except Exception:
                    line = raw.decode("latin-1", errors="replace").strip()
                if not line or line.startswith("-"):
                    continue

                # Detect header
                if line.lower().startswith("id,"):
                    new_header = [c.strip() for c in line.split(",")]
                    with serial_lock:
                        if serial_header != new_header:
                            serial_header = new_header
                            serial_buffer.clear()  # RESET the buffer
                            print(f"[serial_reader] NEW header detected, buffer cleared: {serial_header}")
                    continue

                # Append rows after header
                if serial_header is not None:
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) != len(serial_header):
                        continue
                    row = dict(zip(serial_header, parts))
                    with serial_lock:
                        serial_buffer.append(row)
                        if len(serial_buffer) > MAX_BUFFER_LINES:
                            serial_buffer.pop(0)
                    # Print row in CSV format like your example
                    csv_line = ",".join(str(row[col]) for col in serial_header)
                    print(f"{csv_line}")

        except Exception as e:
            print("[serial_worker] exception:", e)
            time.sleep(1)

# ---------------- LOAD DATA ----------------
def load_data():
    global serial_buffer
    with serial_lock:
        if len(serial_buffer) == 0:
            return pd.DataFrame()
        rows_copy = list(serial_buffer)
    df = pd.DataFrame(rows_copy)
    numeric_cols = ["millis","gas_resistance","temperature","pressure","humidity","index","gas_index"]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "status" in df.columns:
        df = df[df["status"].astype(str) == "b0"]
    if "id" in df.columns and "index" in df.columns:
        df["sensor_key"] = df["id"].astype(str) + "_S" + df["index"].astype(str)
    return df

# ---------------- MAKE FIGURE ----------------
def make_figure(df, selected_sensor):
    needed_cols = ["millis","gas_resistance","temperature","pressure","humidity","id","index","status","sensor_key","gas_index"]
    for c in needed_cols:
        if c not in df.columns:
            df[c] = pd.Series(dtype=float if c in ["millis","gas_resistance","temperature","pressure","humidity","index","gas_index"] else object)

    sensors = df["sensor_key"].unique() if "sensor_key" in df.columns else []
    d = df[df["sensor_key"] == selected_sensor].sort_values("millis") if selected_sensor in sensors else pd.DataFrame()

    fig = make_subplots(
        rows=4, cols=2,
        specs=[[{"type":"scatter"},{"type":"table"}],
               [{"type":"scatter"},{"type":"table"}],
               [{"type":"scatter"}, None],
               [{"type":"scatter"}, None]],
        column_widths=[0.65,0.35], row_heights=[0.5,0.17,0.17,0.16],
        shared_xaxes=True, vertical_spacing=0.05
    )

    # --- Gas Resistance Curves ---
    if not d.empty:
        color_map = {
            100: "orange",   # Forced mode calibration
            99: "cyan",      # Forced mode measurement
        }
        parallel_colors = [
            "red","green","blue","purple","magenta",
            "yellow","lime","teal","pink","brown"
        ]
        for gas_idx in sorted(d["gas_index"].unique()):
            if pd.isna(gas_idx):
                continue
            try:
                gi = int(gas_idx)
            except ValueError:
                continue

            sub = d[d["gas_index"].astype(int) == gi]
            if sub.empty:
                continue

            if gi in (99, 100):
                fig.add_trace(go.Scatter(
                    x=sub["millis"], y=sub["gas_resistance"],
                    mode="lines+markers",
                    name=f"Forced {gi}",
                    line=dict(color=color_map.get(gi, "gray")),
                    hovertemplate="Gas: %{y:,.0f} Ω (%{y:.0e})<extra></extra>"
                ), row=1, col=1)
            else:
                fig.add_trace(go.Scatter(
                    x=sub["millis"], y=sub["gas_resistance"],
                    mode="lines+markers",
                    name=f"Step {gi}",
                    line=dict(color=parallel_colors[gi % len(parallel_colors)]),
                    hovertemplate="Gas: %{y:,.0f} Ω (%{y:.0e})<extra></extra>"
                ), row=1, col=1)

    # --- Temperature, Pressure, Humidity ---
    fig.add_trace(go.Scatter(x=d["millis"], y=d["temperature"], mode="lines+markers",
                             name="Temperature (°C)", hovertemplate="%{y:.2f} °C<extra></extra>"), row=2, col=1)
    fig.add_trace(go.Scatter(x=d["millis"], y=d["pressure"], mode="lines+markers",
                             name="Pressure (Pa)", hovertemplate="%{y:.2f} Pa<extra></extra>"), row=3, col=1)
    fig.add_trace(go.Scatter(x=d["millis"], y=d["humidity"], mode="lines+markers",
                             name="Humidity (%)", hovertemplate="%{y:.2f}%<extra></extra>"), row=4, col=1)

    # --- Tables ---
    table_cols = ["id","index","gas_resistance","status","gas_index"] if "gas_index" in d.columns else ["id","index","gas_resistance","status"]
    present_cols = [c for c in table_cols if c in d.columns]
    fig.add_trace(go.Table(
        header=dict(values=[f"<b>{c}</b>" for c in present_cols], fill_color="#111", font=dict(color="white")),
        cells=dict(values=[d[c] for c in present_cols], fill_color="#1f2937", font=dict(color="white"))
    ), row=1, col=2)

    min_v = d["gas_resistance"].min() if not d.empty else 0
    max_v = d["gas_resistance"].max() if not d.empty else 0
    mean_v = d["gas_resistance"].mean() if not d.empty else 0
    fig.add_trace(go.Table(
        header=dict(values=["MIN","MAX","AVG"], fill_color="#111", font=dict(color="white")),
        cells=dict(values=[[f"{min_v:,.2f}"],[f"{max_v:,.2f}"],[f"{mean_v:,.2f}"]],
                    fill_color="#222222", font=dict(color="white"))
    ), row=2, col=2)

    # Layout
    fig.update_layout(template="plotly_dark", title=f"BME688 Dashboard - {selected_sensor}", hovermode="x unified", height=1150, width=1500)
    fig.update_yaxes(title_text="Gas Resistance (Ω, log scale)", row=1, col=1, type="log")
    fig.update_yaxes(title_text="Temperature (°C)", row=2, col=1)
    fig.update_yaxes(title_text="Pressure (Pa)", row=3, col=1)
    fig.update_yaxes(title_text="Humidity (%)", row=4, col=1)
    fig.update_xaxes(title_text="Time (ms)", row=4, col=1, rangeslider_visible=True, rangeslider_thickness=0.10)

    return fig, sensors

# ------------------- DASH APP -------------------
app = Dash(__name__)

app.layout = html.Div([
    html.H2("BME688 Live Dashboard", style={"color":"white","textAlign":"center"}),
    dcc.Dropdown(id="sensor-dropdown", options=[], value=None, style={"width":"400px","margin":"auto"}),
    dcc.Graph(id="live-graph"),
    dcc.Interval(id="interval-refresh", interval=500, n_intervals=0),
    dcc.Store(id="last-count", data=0)
], style={"backgroundColor":"#111","padding":"20px"})

# ------------------- CALLBACKS -------------------
@app.callback(
    [Output("sensor-dropdown", "options"), Output("sensor-dropdown", "value")],
    Input("interval-refresh", "n_intervals"),
    State("sensor-dropdown", "value")
)
def update_sensors(n, current_value):
    df = load_data()
    if df.empty or "sensor_key" not in df.columns:
        return [], None
    sensors = df["sensor_key"].unique()
    value = current_value if current_value in sensors else sensors[0]
    options = [{"label": s, "value": s} for s in sensors]
    return options, value

@app.callback(
    Output("live-graph", "figure"),
    [Input("interval-refresh", "n_intervals"), Input("sensor-dropdown", "value")]
)
def update_graph(n, selected_sensor):
    if selected_sensor is None:
        return go.Figure()
    df = load_data()
    fig, _ = make_figure(df, selected_sensor)
    return fig

# ------------------- MAIN -------------------
if __name__ == "__main__":
    _thread = threading.Thread(target=serial_worker, args=(SERIAL_PORT, BAUDRATE, SERIAL_TIMEOUT), daemon=True)
    _thread.start()
    app.run(debug=True, use_reloader=False)
