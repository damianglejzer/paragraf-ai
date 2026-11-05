import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { wakeBackend } from "./api";
import "./styles.css";

wakeBackend();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
