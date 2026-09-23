export { Alert } from "./Alert";
export type { AlertProps } from "./Alert";

export { Avatar } from "./Avatar";
export type { AvatarProps } from "./Avatar";

export { Badge, StatusBadge, PriorityBadge, SemPrioridade, TagBadge } from "./Badge";
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

// O `Select` e o `SelectMenu` sao o MESMO papel em duas encarnacoes, e a
// divisao do trabalho continua sendo a da D9.2 -- quem escreve a lista:
//
//   lista fechada, escrita no codigo  -> `SelectMenu`
//   lista que vem da rede e cresce    -> `Selector variant="filter"`, com busca
//
// O que mudou foi so o CONTROLE do lado fechado: era o `<select>` nativo, que
// abria uma lista desenhada pelo sistema operacional -- fora do tema, sem os
// tokens do pacote e diferente em cada navegador --, e passou a ser um painel
// nosso, no desenho do `SelectMenu` do HS Growth.
//
// O `Select` fica `@deprecated` e sem chamada nenhuma. Ele nao foi removido no
// mesmo passo de proposito: e o que a D9.2 fez com o `FilterSelect`, primeiro
// esvaziar, depois tirar.
export { SelectMenu } from "./SelectMenu";
export type { SelectMenuProps, SelectMenuOption } from "./SelectMenu";

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
