// fetch wrapper: JSON in, JSON out, throws Error(detail) on non-2xx.
export async function api(method, path, body) {
  const opts = { method, headers: {}, credentials: 'same-origin' };
  if (body instanceof FormData) {
    opts.body = body;
  } else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  const isJson = (res.headers.get('content-type') || '').includes('json');
  const data = isJson ? await res.json() : null;
  if (!res.ok) {
    const detail = data?.detail;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail) || res.statusText);
  }
  return data;
}
