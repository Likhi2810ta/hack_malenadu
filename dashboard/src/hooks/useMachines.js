import { useState, useEffect, useRef } from 'react'

const API = 'http://localhost:8000'

const ORDERED = ['CNC_01', 'CNC_02', 'PUMP_03', 'CONVEYOR_04']

export function useMachines() {
  const [machines, setMachines] = useState({})
  const [connected, setConnected] = useState(false)
  const esRef = useRef(null)

  useEffect(() => {
    function connect() {
      const es = new EventSource(`${API}/api/stream`)
      esRef.current = es

      es.onopen = () => setConnected(true)

      es.onmessage = (e) => {
        try {
          const event = JSON.parse(e.data)
          if (event.type === 'machine_update' && event.data?.id) {
            setMachines(prev => ({ ...prev, [event.data.id]: event.data }))
          }
        } catch (_) {}
      }

      es.onerror = () => {
        setConnected(false)
        es.close()
        setTimeout(connect, 3000)
      }
    }

    connect()
    return () => esRef.current?.close()
  }, [])

  const ordered = ORDERED.map(id => machines[id]).filter(Boolean)

  return { machines, ordered, connected }
}

export async function fetchHistory(machineId) {
  const res = await fetch(`${API}/api/machines/${machineId}/history?n=30`)
  return res.json()
}

export async function confirmMaintenance(machineId) {
  await fetch(`${API}/api/machines/${machineId}/confirm`, { method: 'POST' })
}

export async function dismissAlarm(machineId) {
  await fetch(`${API}/api/machines/${machineId}/dismiss`, { method: 'POST' })
}
