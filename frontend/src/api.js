import axios from "axios";

// Same-origin in production (Flask serves the bundle); Vite proxies in dev.
const api = axios.create({ baseURL: "" });

export const listEvents = (params) =>
  api.get("/api/events", { params }).then((r) => r.data);

export const createEvent = (payload) =>
  api.post("/api/events", payload).then((r) => r.data);

export const updateEvent = (id, payload) =>
  api.put(`/api/events/${id}`, payload).then((r) => r.data);

export const deleteEvent = (id) =>
  api.delete(`/api/events/${id}`).then((r) => r.data);

export const searchImages = (q) =>
  api.get("/api/image-search", { params: { q } }).then((r) => r.data.results);

export const searchSetlists = (artist, date) =>
  api.get("/api/setlist-search", { params: { artist, date } }).then((r) => r.data);

export const setImageByUrl = (id, url) =>
  api.post(`/api/events/${id}/image`, { url }).then((r) => r.data);

export const setImageByFile = (id, file) => {
  const fd = new FormData();
  fd.append("file", file);
  return api.post(`/api/events/${id}/image`, fd).then((r) => r.data);
};

export const importBackup = (file) => {
  const fd = new FormData();
  fd.append("file", file);
  return api.post("/api/import", fd).then((r) => r.data);
};

export default api;
