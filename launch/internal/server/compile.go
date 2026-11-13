package server

import (
	"crypto/subtle"
	"context"
	"net/http"
	"time"

	"circuitpathways/internal/arduino"
)

type compileRequest struct {
	Code    string `json:"code"`
	Board   string `json:"board"`
	Variant string `json:"variant"`
}

type artifactJSON struct {
	Name   string `json:"name"`
	Offset int    `json:"offset"`
	Data   []byte `json:"data"` // base64
}

type compileResponse struct {
	OK        bool                 `json:"ok"`
	Output    string               `json:"output"`
	Errors    []arduino.Diagnostic `json:"errors"`
	Size      *arduino.Size        `json:"size,omitempty"`
	Artifacts []artifactJSON       `json:"artifacts,omitempty"`
}

// handleCompile compiles a sketch. The code is held in memory and in a
// temporary folder for this one request and is never kept or logged.
func (s *Server) handleCompile(w http.ResponseWriter, r *http.Request) {
	if s.limited(w, r, s.limits.compile) {
		return
	}
	if v := r.Header.Get(accessHeader); !s.Signer.CheckAccess(v, s.Now()) && !(s.Beta && v == "beta") && !s.compileKeyOK(r) {
		writeError(w, http.StatusUnauthorized, "no_class", "Join a class with your class code to upload to a board.")
		return
	}
	if s.Compiler == nil {
		writeError(w, http.StatusServiceUnavailable, "no_tools", "Compiling for real boards is switched off on this site. The simulator still works.")
		return
	}
	var req compileRequest
	if !readJSON(w, r, &req) {
		return
	}
	if req.Code == "" || len(req.Code) > maxSketchSize {
		writeError(w, http.StatusBadRequest, "bad_code", "This sketch is too long (the limit is 100 KB).")
		return
	}
	b, ok := s.Catalogue.Board(req.Board)
	if !ok {
		writeError(w, http.StatusBadRequest, "bad_board", "Pick one of the boards on the list.")
		return
	}
	fqbn := b.FQBN
	if req.Variant != "" {
		fqbn = ""
		for _, v := range b.Variants {
			if v.ID == req.Variant {
				fqbn = v.FQBN
			}
		}
		if fqbn == "" {
			writeError(w, http.StatusBadRequest, "bad_board", "That board setting doesn't match the board.")
			return
		}
	}

	ctx, cancel := context.WithTimeout(r.Context(), compileWait+5*time.Minute)
	defer cancel()
	select {
	case s.slots <- struct{}{}:
		defer func() { <-s.slots }()
	case <-time.After(compileWait):
		w.Header().Set("Retry-After", "20")
		writeError(w, http.StatusServiceUnavailable, "busy", "Lots of students are uploading right now. Wait a moment and press Upload again.")
		return
	case <-ctx.Done():
		return
	}
	res, arts, err := s.Compiler.Compile(ctx, req.Code, fqbn, b.BuildProperties)
	if err != nil {
		s.Log.Error("compile", "board", req.Board, "err", err.Error())
		writeError(w, http.StatusBadGateway, "compile_failed", "The compiler had a problem. Try again in a moment.")
		return
	}
	out := compileResponse{OK: res.OK, Output: res.Output, Errors: res.Diagnostics, Size: res.Size}
	if out.Errors == nil {
		out.Errors = []arduino.Diagnostic{}
	}
	for _, a := range arts {
		out.Artifacts = append(out.Artifacts, artifactJSON{Name: a.Name, Offset: a.Offset, Data: a.Data})
	}
	writeJSON(w, http.StatusOK, out)
}

// compileKeyOK: the request comes from a front end this server compiles for (see Config.CompileKey).
func (s *Server) compileKeyOK(r *http.Request) bool {
	k := r.Header.Get("X-Compile-Key")
	return len(s.CompileKey) >= 16 && subtle.ConstantTimeCompare([]byte(k), []byte(s.CompileKey)) == 1
}
