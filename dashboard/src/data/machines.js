export const initialMachines = [
  {
    id: 'CNC_01',
    name: 'Precision CNC Mill',
    model: 'HAAS VF-2SS',
    location: 'Bay A-1',
    machineType: 'cnc',
    status: 'healthy',
    risk: 12,
    temperature: 68.2,
    vibration: 1.2,
    rpm: 4820,
    current: 8.4,
    efficiency: 94,
    uptime: 99.2,
    lastService: '12 days ago',
    hoursRun: 1284,
  },
  {
    id: 'CNC_02',
    name: 'CNC Lathe Unit',
    model: 'Mazak QT-200',
    location: 'Bay A-2',
    machineType: 'cnc',
    status: 'warning',
    risk: 67,
    temperature: 78.5,
    vibration: 3.8,
    rpm: 3240,
    current: 12.1,
    efficiency: 76,
    uptime: 94.1,
    lastService: '31 days ago',
    hoursRun: 2106,
  },
  {
    id: 'PUMP_03',
    name: 'Hydraulic Pump Unit',
    model: 'Parker P2-060',
    location: 'Bay B-1',
    machineType: 'pump',
    status: 'critical',
    risk: 89,
    temperature: 91.4,
    vibration: 7.2,
    rpm: 2180,
    current: 18.6,
    efficiency: 52,
    uptime: 78.3,
    lastService: '58 days ago',
    hoursRun: 3947,
  },
  {
    id: 'CONVEYOR_04',
    name: 'Belt Conveyor System',
    model: 'Hytrol E-Z 24',
    location: 'Bay C-1',
    machineType: 'conveyor',
    status: 'healthy',
    risk: 8,
    temperature: 42.1,
    vibration: 0.8,
    rpm: 1200,
    current: 5.2,
    efficiency: 97,
    uptime: 99.8,
    lastService: '5 days ago',
    hoursRun: 872,
  },
]

export function generateSeries(base, variance, points = 24, trend = 0) {
  const arr = []
  let val = base
  for (let i = 0; i < points; i++) {
    val += (Math.random() - 0.48) * variance + trend
    val = Math.max(base * 0.6, Math.min(base * 1.6, val))
    arr.push({ t: i, v: parseFloat(val.toFixed(2)) })
  }
  return arr
}
