export { Alert } from "./Alert";
export type { AlertProps } from "./Alert";

export { Avatar } from "./Avatar";
export type { AvatarProps } from "./Avatar";

export { Badge, StatusBadge, PriorityBadge, TagBadge } from "./Badge";
export type { BadgeProps } from "./Badge";

export { Button } from "./Button";
export type { ButtonProps } from "./Button";

export { Card, CardHeader, CardTitle } from "./Card";
export type { CardProps } from "./Card";

export { Checkbox } from "./Checkbox";
export type { CheckboxProps } from "./Checkbox";

export { Icon, ICON_PATHS } from "./Icon";
export type { IconProps, IconName } from "./Icon";

export { KpiCard } from "./KpiCard";
export type { KpiCardProps, KpiTone } from "./KpiCard";

export { Input } from "./Input";
export type { InputProps } from "./Input";

export { Modal, ModalFooter } from "./Modal";
export type { ModalProps } from "./Modal";

export { Switch } from "./Switch";
export type { SwitchProps } from "./Switch";

// O seletor unico da Fase 8. `FormDropdown` e `SearchSelect` continuam
// exportados como involucros @deprecated; chamada nova usa este.
//
// O `FilterSelect` SAIU na D9.2, e a ordem importa: ele foi removido depois
// de as dezessete chamadas dele virarem `<Select>` nativo ou
// `Selector variant="filter"` -- nao antes. O defeito que ele carregava era
// nao repassar `label`, entao cada filtro se anunciava pelo VALOR ("Ativos")
// sem dizer de que filtro era. Os comentarios das telas que ainda o citam
// registram isso de proposito.
export { Selector } from "./Selector";
export type { SelectorProps, SelectorOption } from "./Selector";

export { RadioCards } from "./RadioCards";
export type { RadioCardsProps, RadioOption, RadioTone } from "./RadioCards";

export { Select } from "./Select";
export type { SelectProps, SelectOption } from "./Select";

export { FileUpload } from "./FileUpload";
export type { FileUploadProps } from "./FileUpload";


export { FormDropdown } from "./FormDropdown";
export type { FormDropdownProps, FormDropdownOption } from "./FormDropdown";
export { SearchSelect } from "./SearchSelect";
export type { SearchSelectProps, SearchSelectOption } from "./SearchSelect";

export { SlaChip } from "./SlaChip";
export type { SlaChipProps } from "./SlaChip";

export { Spinner } from "./Spinner";

export {
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableHeaderCell,
  TableCell,
  TableEmpty,
} from "./Table";
export type {
  TableProps,
  TableRowProps,
  TableHeaderCellProps,
  TableCellProps,
} from "./Table";

export { Pagination } from "./Pagination";
export type { PaginationProps } from "./Pagination";

export { TicketFilters, EMPTY_FILTERS } from "./TicketFilters";
export type { TicketFilterState, TicketFiltersProps } from "./TicketFilters";

export { Tooltip } from "./Tooltip";
export type { TooltipProps } from "./Tooltip";
export { Tabs, TabsList, TabsTrigger, TabsContent } from "./Tabs";
export type { TabsProps, TabsTriggerProps, TabsContentProps } from "./Tabs";

export { Textarea } from "./Textarea";
export type { TextareaProps } from "./Textarea";
