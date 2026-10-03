# Sugarcane Pest System frontend

Use http://localhost:3000 as the local browser address. The Flask API runs internally at http://127.0.0.1:5000. Next.js rewrites browser requests under /api/ to that backend, so browser authentication uses same-origin URLs and the Flask HttpOnly cookie belongs to localhost.

Set BACKEND_API_URL on the Next.js server if the backend address differs. See .env.example. Do not use a NEXT_PUBLIC_ variable for the backend address. Restart Next.js after changing this setting.

From the frontend directory, run:

    npm.cmd run dev

Then open http://localhost:3000/login. After signing in, /dashboard restores the session through GET /api/v1/auth/me on refresh. Logout sends the in-memory CSRF token in X-CSRF-Token. Browser code does not read or store the HttpOnly session cookie.

Verification commands:

    npm.cmd run lint
    npx.cmd tsc --noEmit
    npm.cmd run build

The dashboard is an authentication placeholder. Business dashboard features belong to a later phase.
