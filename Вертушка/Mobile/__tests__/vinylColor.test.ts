import { parseVinylColor } from '../lib/vinylColor';

const BLACK = '#1A1A1A';

describe('parseVinylColor — двухцветный пресс', () => {
  it('чёрный рядом с цветом становится вторым цветом брызг', () => {
    const c = parseVinylColor('red & black splatter');
    expect(c.type).toBe('splatter');
    expect(c.primaryColor).toBe('#E53935');
    expect(c.secondaryColor).toBe(BLACK);
  });

  it('Discogs-строка с чёрным разводом', () => {
    const c = parseVinylColor('Orange With Black Marbled');
    expect(c.type).toBe('marble');
    expect(c.secondaryColor).toBe(BLACK);
  });

  it('два цвета без узора — cic', () => {
    const c = parseVinylColor('red & blue');
    expect(c.type).toBe('cic');
    expect(c.secondaryColor).toBe('#1E88E5');
  });

  it('swirl двумя цветами', () => {
    const c = parseVinylColor('Red And Gold Swirl');
    expect(c.type).toBe('swirl');
    expect(c.secondaryColor).toBeDefined();
  });

  it('одиночный чёрный — обычная пластинка', () => {
    expect(parseVinylColor('Black').isColored).toBe(false);
    expect(parseVinylColor('Black, 180g').isColored).toBe(false);
  });

  it('один цвет — без второго', () => {
    expect(parseVinylColor('Red').secondaryColor).toBeUndefined();
  });
});

describe('parseVinylColor — порядок и составные цвета', () => {
  it('составной ключ не порождает второй цвет', () => {
    expect(parseVinylColor('Sky Blue').secondaryColor).toBeUndefined();
  });

  it('основной цвет — первый по тексту', () => {
    expect(parseVinylColor('Blue & Red').primaryColor).toBe('#1E88E5');
  });
});
