/*
Copyright The Kubernetes Authors.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package proxy

import (
	"encoding/json"
	"errors"
	"net/http"
	"time"

	"proxy-production-system/internal/model"
	"proxy-production-system/internal/store"
)

func (g *Gateway) registerAdminRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/v1/backends", g.handleListBackends)
	mux.HandleFunc("POST /api/v1/backends", g.handleCreateBackend)
	mux.HandleFunc("GET /api/v1/backends/{id}", g.handleGetBackend)
	mux.HandleFunc("PUT /api/v1/backends/{id}", g.handleUpdateBackend)
	mux.HandleFunc("DELETE /api/v1/backends/{id}", g.handleDeleteBackend)
	mux.HandleFunc("POST /api/v1/pool/reload", g.handleReloadPool)
}

func (g *Gateway) handleListBackends(w http.ResponseWriter, r *http.Request) {
	if !g.authorizeAdmin(r) {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	backends, err := g.sync.Repository().List(r.Context())
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	writeJSON(w, http.StatusOK, backends)
}

func (g *Gateway) handleCreateBackend(w http.ResponseWriter, r *http.Request) {
	if !g.authorizeAdmin(r) {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}

	var backend model.ProxyBackend
	if err := json.NewDecoder(r.Body).Decode(&backend); err != nil {
		http.Error(w, "invalid json body", http.StatusBadRequest)
		return
	}
	backend.Normalize(time.Now())
	if err := g.sync.Repository().Create(r.Context(), &backend); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if err := g.sync.ReloadNow(r.Context()); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	writeJSON(w, http.StatusCreated, backend)
}

func (g *Gateway) handleGetBackend(w http.ResponseWriter, r *http.Request) {
	if !g.authorizeAdmin(r) {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	backend, err := g.sync.Repository().Get(r.Context(), r.PathValue("id"))
	if err != nil {
		writeStoreError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, backend)
}

func (g *Gateway) handleUpdateBackend(w http.ResponseWriter, r *http.Request) {
	if !g.authorizeAdmin(r) {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}

	var backend model.ProxyBackend
	if err := json.NewDecoder(r.Body).Decode(&backend); err != nil {
		http.Error(w, "invalid json body", http.StatusBadRequest)
		return
	}
	backend.ID = r.PathValue("id")
	if err := g.sync.Repository().Update(r.Context(), backend); err != nil {
		writeStoreError(w, err)
		return
	}
	if err := g.sync.ReloadNow(r.Context()); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	writeJSON(w, http.StatusOK, backend)
}

func (g *Gateway) handleDeleteBackend(w http.ResponseWriter, r *http.Request) {
	if !g.authorizeAdmin(r) {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	if err := g.sync.Repository().Delete(r.Context(), r.PathValue("id")); err != nil {
		writeStoreError(w, err)
		return
	}
	if err := g.sync.ReloadNow(r.Context()); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (g *Gateway) handleReloadPool(w http.ResponseWriter, r *http.Request) {
	if !g.authorizeAdmin(r) {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	if err := g.sync.ReloadNow(r.Context()); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	writeJSON(w, http.StatusOK, g.manager.Stats())
}

func writeStoreError(w http.ResponseWriter, err error) {
	if errors.Is(err, store.ErrNotFound) {
		http.Error(w, "backend not found", http.StatusNotFound)
		return
	}
	http.Error(w, err.Error(), http.StatusInternalServerError)
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}
