// Groups the catalogue's garment colors ("navy blue", "heather gray", "cream", ...)
// into a short list of colors to filter by. Filtering uses each product's
// primary_color — the color of the garment itself, not its logo or lettering.
export interface ColorGroup {
  name: string
  swatch: string
  matches: (color: string) => boolean
}

export const COLOR_GROUPS: ColorGroup[] = [
  { name: 'Navy', swatch: '#00356b', matches: (c) => c.includes('navy') },
  { name: 'Blue', swatch: '#4a90d9', matches: (c) => c.includes('blue') && !c.includes('navy') },
  { name: 'Gray', swatch: '#9aa3ad', matches: (c) => c.includes('gray') || c.includes('charcoal') },
  { name: 'White', swatch: '#ffffff', matches: (c) => ['white', 'cream', 'ivory'].some((w) => c.includes(w)) },
  { name: 'Black', swatch: '#1b1b1b', matches: (c) => c.includes('black') },
  { name: 'Red', swatch: '#c8102e', matches: (c) => c.includes('red') },
  { name: 'Coral', swatch: '#e8857a', matches: (c) => c.includes('coral') || c.includes('pink') },
  { name: 'Gold', swatch: '#e0b23a', matches: (c) => c.includes('yellow') || c.includes('gold') },
  { name: 'Green', swatch: '#2e7d4f', matches: (c) => c.includes('green') },
]

export function garmentColorIs(primaryColor: string | null, group: string): boolean {
  const g = COLOR_GROUPS.find((x) => x.name === group)
  return !!g && !!primaryColor && g.matches(primaryColor.toLowerCase())
}
