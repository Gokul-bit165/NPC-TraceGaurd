/**
 * Exports an array of objects to a downloadable CSV file.
 * @param {Array<Object>} rows - Data rows to export
 * @param {string} filename - Desired filename (e.g., 'traceguard-logins.csv')
 * @param {Array<{ key: string, label: string, formatter?: (val: any, row: any) => string }>} columns - Column definitions
 */
export function exportToCsv(rows, filename = 'export.csv', columns = []) {
  if (!rows || rows.length === 0) {
    alert('No data available to export.')
    return
  }

  // Derive columns if not provided
  const cols = columns.length > 0
    ? columns
    : Object.keys(rows[0]).map((k) => ({ key: k, label: k }))

  const headers = cols.map((c) => escapeCsvValue(c.label)).join(',')
  
  const csvLines = rows.map((row) => {
    return cols
      .map((col) => {
        let val = row[col.key]
        if (col.formatter) {
          val = col.formatter(val, row)
        } else if (val && typeof val === 'object') {
          val = JSON.stringify(val)
        }
        return escapeCsvValue(val)
      })
      .join(',')
  })

  const csvContent = [headers, ...csvLines].join('\r\n')
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.setAttribute('href', url)
  link.setAttribute('download', filename.endsWith('.csv') ? filename : `${filename}.csv`)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

function escapeCsvValue(value) {
  if (value === null || value === undefined) return '""'
  const stringValue = String(value)
  // Escape double quotes by doubling them
  const escaped = stringValue.replace(/"/g, '""')
  return `"${escaped}"`
}
