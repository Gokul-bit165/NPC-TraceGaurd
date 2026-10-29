import React from 'react'
import { Search, X } from 'lucide-react'

export default function SearchBar({
  value = '',
  onChange,
  onClear,
  placeholder = 'Search…',
  className = '',
}) {
  return (
    <div className={`relative flex items-center ${className}`}>
      <Search
        className="pointer-events-none absolute left-3 text-slate-500"
        size={16}
      />
      <input
        type="text"
        className="input !pl-9 !pr-8"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
      {value && (
        <button
          type="button"
          onClick={() => {
            if (onClear) onClear()
            else onChange('')
          }}
          className="absolute right-2.5 text-slate-500 hover:text-slate-300"
          aria-label="Clear search"
        >
          <X size={14} />
        </button>
      )}
    </div>
  )
}
