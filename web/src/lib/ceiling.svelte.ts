const KEY = 'cc.ceiling';
const DEFAULT = 3000;

function read(): number {
  if (typeof localStorage === 'undefined') return DEFAULT;
  const v = Number(localStorage.getItem(KEY));
  return Number.isFinite(v) && v > 0 ? v : DEFAULT;
}

let _value = $state(read());

export const ceiling = {
  get value() { return _value; },
  set(n: number) {
    _value = n > 0 ? n : DEFAULT;
    if (typeof localStorage !== 'undefined') localStorage.setItem(KEY, String(_value));
  }
};
