/**
 * Joins class names, filtering out falsy values.
 * Lightweight alternative to clsx for simple use cases.
 */
export function cn(...classes: (string | undefined | false | null)[]): string {
  return classes.filter(Boolean).join(" ");
}
