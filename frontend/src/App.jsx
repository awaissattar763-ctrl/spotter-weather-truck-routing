import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'

const API_BASE = import.meta.env.VITE_API_BASE || ''

const RISK_COLORS = {
  Low: '#22a06b',
  Moderate: '#d9a400',
  High: '#e06a00',
  Severe: '#c81e1e',
  'No Travel': '#111111',
  Unknown: '#888888',
}

function fmtEta(iso) {
  try {
    return new Date(iso).toLocaleString([], {
      month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function defaultDeparture() {
  const d = new Date(Date.now() + 24 * 3600 * 1000)
  d.setMinutes(0, 0, 0)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export default function App() {
  const [origin, setOrigin] = useState('Dallas, TX')
  const [destination, setDestination] = useState('Houston, TX')
  const [departure, setDeparture] = useState(defaultDeparture())
  const [load, setLoad] = useState(35000)
  const [interval, setInterval] = useState(25)
  const [shift, setShift] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [selected, setSelected] = useState(0)

  const mapDiv = useRef(null)
  const mapRef = useRef(null)
  const layerRef = useRef(null)

  useEffect(() => {
    if (!mapDiv.current || mapRef.current) return
    const map = L.map(mapDiv.current).setView([32.8, -96.8], 6)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map)
    mapRef.current = map
    layerRef.current = L.layerGroup().addTo(map)
    return () => { map.remove(); mapRef.current = null }
  }, [])

  // Draw routes + checkpoints + corridor heat whenever result/selection changes.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !result) return
    const layer = layerRef.current
    layer.clearLayers()
    const bounds = []
    result.routes.forEach((route, ri) => {
      const latlngs = route.geometry.map(([lon, lat]) => [lat, lon])
      latlngs.forEach((p) => bounds.push(p))
      const isSelected = ri === selected
      // Faint full geometry for every route.
      L.polyline(latlngs, {
        color: isSelected ? '#334155' : '#94a3b8',
        weight: isSelected ? 3 : 2,
        opacity: isSelected ? 0.9 : 0.5,
      }).addTo(layer)
      if (!isSelected) return
      // Corridor heat: thick translucent segments between checkpoints,
      // colored by the starting checkpoint's risk.
      const cps = route.checkpoints
      for (let i = 0; i < cps.length - 1; i++) {
        L.polyline([[cps[i].lat, cps[i].lon], [cps[i + 1].lat, cps[i + 1].lon]], {
          color: RISK_COLORS[cps[i].risk] || '#888888',
          weight: 12,
          opacity: 0.35,
        }).addTo(layer)
      }
      cps.forEach((cp) => {
        const marker = L.circleMarker([cp.lat, cp.lon], {
          radius: 7,
          color: '#ffffff',
          weight: 2,
          fillColor: RISK_COLORS[cp.risk] || '#888888',
          fillOpacity: 0.95,
        })
        marker.bindPopup(
          `<b>${cp.risk}</b> — ${cp.miles_from_start} mi<br/>` +
          `ETA ${fmtEta(cp.eta)}<br/>` +
          `Wind ${cp.wind_mph ?? '—'} mph · Rain ${cp.rain_in_hr ?? '—'} in/hr · ` +
          `Snow ${cp.snow_in_hr ?? '—'} in/hr`,
        )
        marker.addTo(layer)
      })
    })
    if (bounds.length) map.fitBounds(bounds, { padding: [30, 30] })
  }, [result, selected])

  async function plan(tShift = shift) {
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const resp = await fetch(`${API_BASE}/api/plan/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          origin,
          destination,
          departure: new Date(departure).toISOString(),
          load_weight_lb: Number(load),
          interval_miles: Number(interval),
          time_shift_hours: Number(tShift),
        }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.error || 'Planning failed')
      setResult(data)
      setSelected(data.recommended_route_index ?? 0)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function onShiftChange(value) {
    setShift(value)
    if (result) plan(value)
  }

  const selectedRoute = result?.routes?.[selected]

  return (
    <div className="app">
      <header>
        <h1>Weather-Aware Truck Routing</h1>
        <p>Pick the safest route by weather, load weight, and travel time.</p>
      </header>

      <section className="form">
        <label>Origin
          <input value={origin} onChange={(e) => setOrigin(e.target.value)} />
        </label>
        <label>Destination
          <input value={destination} onChange={(e) => setDestination(e.target.value)} />
        </label>
        <label>Departure
          <input type="datetime-local" value={departure} onChange={(e) => setDeparture(e.target.value)} />
        </label>
        <label>Load weight (lb)
          <input type="number" value={load} onChange={(e) => setLoad(e.target.value)} />
        </label>
        <label>Weather sampling
          <select value={interval} onChange={(e) => setInterval(e.target.value)}>
            <option value={10}>Every 10 miles</option>
            <option value={25}>Every 25 miles</option>
            <option value={50}>Every 50 miles</option>
          </select>
        </label>
        <button onClick={() => plan()} disabled={loading}>
          {loading ? 'Planning…' : 'Plan routes'}
        </button>
      </section>

      {error && <p className="error">Error: {error}</p>}
      {result?.note && <p className="note">{result.note}</p>}

      {result && (
        <>
          <section className="slider">
            <label>
              Forecast slider — shift trip start by <b>{shift}h</b> (0–48h).
              Checkpoint risks are recomputed for the shifted start time.
              <input
                type="range" min="0" max="48" step="1" value={shift}
                onChange={(e) => onShiftChange(Number(e.target.value))}
              />
            </label>
            <span>Effective departure: {fmtEta(result.effective_departure)}</span>
          </section>

          <section className="routes">
            {result.routes.map((route, i) => (
              <article
                key={i}
                className={`route-card ${i === selected ? 'selected' : ''} ${i === result.recommended_route_index ? 'recommended' : ''}`}
                onClick={() => setSelected(i)}
              >
                <h3>
                  Route {i + 1}
                  {i === result.recommended_route_index && <span className="badge">★ Recommended</span>}
                </h3>
                <p>{route.distance_miles} mi · {route.duration_minutes} min{route.alternative_method === 'via_waypoint' ? ' · via detour' : ''}</p>
                <p>
                  Severe {route.miles_by_risk.Severe} mi · High {route.miles_by_risk.High} mi ·{' '}
                  No Travel {route.miles_by_risk['No Travel']} mi · Avg risk {route.avg_risk ?? 'unknown'}
                </p>
                <p className="small">
                  Low {route.miles_by_risk.Low} mi · Moderate {route.miles_by_risk.Moderate} mi ·{' '}
                  {route.checkpoints.length} checkpoints
                </p>
              </article>
            ))}
          </section>
          {result.recommended_route_index != null && (
            <p className="reason">{result.recommendation_reason}</p>
          )}

          <div ref={mapDiv} className="map" />

          {selectedRoute && (
            <section className="checkpoints">
              <h2>Checkpoints — Route {selected + 1}</h2>
              <table>
                <thead>
                  <tr><th>Mi</th><th>ETA</th><th>Wind (mph)</th><th>Rain (in/hr)</th><th>Snow (in/hr)</th><th>Risk</th></tr>
                </thead>
                <tbody>
                  {selectedRoute.checkpoints.map((cp, i) => (
                    <tr key={i}>
                      <td>{cp.miles_from_start}</td>
                      <td>{fmtEta(cp.eta)}</td>
                      <td>{cp.wind_mph ?? '—'}</td>
                      <td>{cp.rain_in_hr ?? '—'}</td>
                      <td>{cp.snow_in_hr ?? '—'}</td>
                      <td><span className="risk" style={{ background: RISK_COLORS[cp.risk] }}>{cp.risk}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
        </>
      )}

      <footer>
        <p>
          Routes: OSRM public demo server · Geocoding: Nominatim · Weather: Open-Meteo forecast (hourly).
          Weather is sampled at each checkpoint's estimated arrival time. See README for limits.
        </p>
      </footer>
    </div>
  )
}
