# Barbara Cluster Actions Sample

Aplicación Python mínima y pipeline de GitHub Actions que despliega en un **cluster de Barbara** ya existente. Está adaptado de [barbara_github_actions_sample](https://github.com/Barbaraedge/barbara_github_actions_sample), que despliega a nodos individuales.

## Pipeline

Se lanza al hacer push de un tag `v*` (`git tag v0.1.0 && git push --tags`):

1. **test** – tests unitarios.
2. **validate-target-cluster** – comprueba que el cluster de `deployment-targets.json` existe en Barbara; si no, falla antes de construir y lista los clusters disponibles.
3. **build-image** – imagen multi-arquitectura a Docker Hub (`<sha>`, `<version>`, `latest`).
4. **package-artifact** – `.zip` con un `docker-compose.yaml` que referencia la imagen `<sha>`.
5. **register-barbara-application** / **upload-barbara-version** – crea la app si falta y sube la versión.
6. **deploy-to-cluster** – crea (o actualiza) el workload de la app en el cluster (`/api/v1/clusters/{id}/user/stacks`).
7. **verify-deployment** – espera a que todos los servicios del workload corran la imagen nueva con sus tareas en `running`; si falla o expira, hace rollback a la versión anterior (o borra el workload) y elimina la versión fallida.
8. **create-github-release** – solo si la verificación fue correcta.

## Destino

`deployment-targets.json`:

```json
{ "cluster": "my-cluster-name" }
```

El nombre debe coincidir con el de un cluster visible en Barbara Panel.

## Configuración en GitHub

**Variables del repositorio:** `APP_NAME`, `IMAGE_NAME`, `DOCKERHUB_NAMESPACE`, `APP_DEVELOPER`, `APP_SHORT_DESCRIPTION`, `APP_LONG_DESCRIPTION`, `APP_VERSION_ARCHITECTURES` (p. ej. `x86_64,arm64`).

**Secrets del repositorio:** `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`.

**Entorno `production`** – variables: `BARBARA_API_URL` (`https://prod.bap.barbara.tech`), `BARBARA_AUTH_URL` (`https://prod.auth.barbara.tech`), `BARBARA_KEYCLOAK_REALM`, `BARBARA_KEYCLOAK_CLIENT_ID`, `BARBARA_KEYCLOAK_USER_EMAIL`, `VERIFY_TIMEOUT_SECONDS`, `VERIFY_INTERVAL_SECONDS`. Secrets: `BARBARA_KEYCLOAK_CLIENT_SECRET`, `BARBARA_KEYCLOAK_USER_PASSWORD`.

Las credenciales Keycloak (client id/secret) las emite el soporte de Barbara.

## Desarrollo local

```bash
python app/main.py                           # http://localhost:8080
python -m unittest discover -s tests -v      # tests
docker compose up --build
```
