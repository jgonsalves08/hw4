import { formatPrice } from '../api'

interface Props {
  min: number
  max: number
  low: number
  high: number
  onChange: (low: number, high: number) => void
}

// Two range inputs stacked on one track, so each end can be dragged separately,
// plus number boxes for typing an exact price.
export default function PriceRangeSlider({ min, max, low, high, onChange }: Props) {
  const span = max - min || 1
  const lowPct = ((low - min) / span) * 100
  const highPct = ((high - min) / span) * 100
  const clamp = (v: number) => Math.min(max, Math.max(min, Number.isFinite(v) ? v : min))
  // Typed prices apply on Enter or when the box loses focus, not on every keystroke.
  const commitOnEnter = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') e.currentTarget.blur()
  }

  return (
    <div className="price-range">
      <div className="price-range-track">
        <div className="price-range-fill" style={{ left: `${lowPct}%`, width: `${highPct - lowPct}%` }} />
        <input
          type="range"
          min={min}
          max={max}
          step={1}
          value={low}
          onChange={(e) => onChange(Math.min(Number(e.target.value), high), high)}
          aria-label="Minimum price"
        />
        <input
          type="range"
          min={min}
          max={max}
          step={1}
          value={high}
          onChange={(e) => onChange(low, Math.max(Number(e.target.value), low))}
          aria-label="Maximum price"
        />
      </div>
      <div className="price-inputs">
        <label>
          <span>$</span>
          <input
            key={low}
            type="number"
            min={min}
            max={high}
            defaultValue={low}
            onBlur={(e) => onChange(Math.min(clamp(Number(e.target.value)), high), high)}
            onKeyDown={commitOnEnter}
            aria-label="Minimum price in dollars"
          />
        </label>
        <span className="dash">–</span>
        <label>
          <span>$</span>
          <input
            key={high}
            type="number"
            min={low}
            max={max}
            defaultValue={high}
            onBlur={(e) => onChange(low, Math.max(clamp(Number(e.target.value)), low))}
            onKeyDown={commitOnEnter}
            aria-label="Maximum price in dollars"
          />
        </label>
      </div>
      <div className="price-range-ends">
        <span>{formatPrice(min)}</span>
        <span>{formatPrice(max)}</span>
      </div>
    </div>
  )
}
