import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../index.css";
import { Galeria } from "./Galeria";

// Sem roteador, sem sessao e sem backend: a galeria mede componentes, nao a
// aplicacao. O tema comeca no CLARO e o teste o alterna pelo botao.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Galeria />
  </StrictMode>,
);
