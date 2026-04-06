import { Routes, Route } from "react-router-dom";
import { AuthProvider } from "./contexts/AuthContext";
import { AppLayout } from "./components/layout/AppLayout";
import HomePage from "./pages/HomePage";

function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* Protected layout — T31 will add the auth guard */}
        <Route element={<AppLayout />}>
          <Route path="/" element={<HomePage />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}

export default App;
