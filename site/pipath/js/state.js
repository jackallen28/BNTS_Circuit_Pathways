// What the whole app shares.
export const state = {
  me: null, // { student, settings }
  catalog: null,
  config: null,
  progress: {}, // lesson id -> saved progress
  runner: null, // the Python runner (started when the first program needs it)
};
