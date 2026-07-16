<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="icon" type="image/png" href="assets/logo.png">
<title>Iniciar sesión — CANAPROSUCRE</title>
<style>
  :root{
    --verde-claro:#8fd14f;
    --verde-oscuro:#4c7a1f;
    --verde-header:#5c9128;
    --azul:#12297a;
    --amarillo:#f6d413;
    --texto-oscuro:#233d0c;
  }
  *{box-sizing:border-box;}
  body{
    margin:0;
    font-family:'Segoe UI', Arial, sans-serif;
    background:linear-gradient(180deg,#a9e06a,#7fc23f);
    min-height:100vh;
    display:flex;
    align-items:center;
    justify-content:center;
    padding:16px;
  }
  .card{
    width:100%;
    max-width:360px;
    background:var(--verde-claro);
    border:4px solid var(--verde-oscuro);
    border-radius:6px;
    overflow:hidden;
    box-shadow:0 8px 24px rgba(0,0,0,.25);
  }
  .header{
    background:var(--verde-header);
    color:#fff;
    padding:20px 18px;
    text-align:center;
  }
  .header .logo{
    width:64px;height:64px;border-radius:50%;
    background:#fff;
    margin:0 auto 10px;
    border:3px solid var(--amarillo);
    overflow:hidden;
  }
  .header .logo img{ width:100%; height:100%; object-fit:contain; }
  .header h1{ margin:0; font-size:16px; text-transform:uppercase; letter-spacing:.4px; }

  form{ padding:22px 20px; }
  label{
    display:block;
    font-weight:700;
    font-size:12px;
    text-transform:uppercase;
    color:var(--texto-oscuro);
    margin-bottom:5px;
  }
  input{
    width:100%;
    padding:10px 12px;
    border-radius:4px;
    border:2px solid var(--verde-oscuro);
    margin-bottom:14px;
    font-size:15px;
  }
  button{
    width:100%;
    background:var(--azul);
    color:#fff;
    border:none;
    padding:12px;
    border-radius:4px;
    font-weight:800;
    font-size:15px;
    letter-spacing:.4px;
    cursor:pointer;
    text-transform:uppercase;
  }
  button:hover{ background:#1a3aa5; }
  .error{
    background:#a33;
    color:#fff;
    padding:9px 12px;
    border-radius:4px;
    font-size:13px;
    font-weight:600;
    margin-bottom:14px;
    display:none;
  }
</style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div class="logo"><img src="assets/logo.png" alt="Logo CANAPROSUCRE"></div>
      <h1>Casa Nacional del Profesor<br>CANAPROSUCRE</h1>
    </div>
    <form id="loginForm">
      <div class="error" id="errorMsg"></div>
      <label>Usuario</label>
      <input type="text" id="username" autocomplete="username" required>
      <label>Contraseña</label>
      <input type="password" id="password" autocomplete="current-password" required>
      <button type="submit">Ingresar</button>
    </form>
  </div>

<script>
const form = document.getElementById("loginForm");
const errorMsg = document.getElementById("errorMsg");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  errorMsg.style.display = "none";

  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;

  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();

    if (!res.ok) {
      errorMsg.textContent = data.error || "No se pudo iniciar sesión.";
      errorMsg.style.display = "block";
      return;
    }

    // Ambos roles caen al buscador; desde ahí el admin puede ir a /admin
    window.location.href = "/";
  } catch (err) {
    errorMsg.textContent = "Error de conexión con el servidor.";
    errorMsg.style.display = "block";
  }
});
</script>
</body>
</html>
