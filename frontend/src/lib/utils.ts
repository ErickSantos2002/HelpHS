type ClassValue =
  | string
  | number
  | boolean
  | null
  | undefined
  | Record<string, boolean | null | undefined>
  | ClassValue[];

/**
 * Joins class names, filtering out falsy values.
 * Supports strings, objects (clsx-style), and arrays.
 */
export function cn(...classes: ClassValue[]): string {
  const result: string[] = [];

  for (const cls of classes) {
    if (!cls) continue;
    if (typeof cls === "string" || typeof cls === "number") {
      result.push(String(cls));
    } else if (Array.isArray(cls)) {
      const nested = cn(...cls);
      if (nested) result.push(nested);
    } else if (typeof cls === "object") {
      for (const [key, value] of Object.entries(cls)) {
        if (value) result.push(key);
      }
    }
  }

  return result.join(" ");
}
