FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# Copy only the dependency list first.
# Docker caches this layer — if requirements.txt doesn't change,
# Docker won't re-install packages on every rebuild, saving time.
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of your actual application code
COPY . .

# Cloud Run injects a PORT environment variable at runtime.
# We default to 8080 locally if PORT isn't set (matches main.py's logic).
ENV PORT=8080

# Document that this container listens on port 8080.
# (This is informational for humans/tools reading the Dockerfile;
# Cloud Run doesn't strictly require EXPOSE, but it's good practice.)
EXPOSE 8080

# Start the FastAPI app using uvicorn, binding to all interfaces (0.0.0.0)
# so it's reachable from outside the container — required for Cloud Run.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]