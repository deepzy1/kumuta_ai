export function errorMessage(data, status) {
  return typeof data.detail === "string"
    ? data.detail
    : `Request failed (${status}). Please try again.`;
}

// Incremental SSE parsing handles UTF-8 split across chunks and multiple events per read.
export async function readEvents(response, onEvent) {
  if (!response.ok)
    throw new Error(
      errorMessage(await response.json().catch(() => ({})), response.status),
    );
  if (!response.body)
    throw new Error("Streaming is unavailable in this browser.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let complete = false;
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const type = frame
          .split("\n")
          .find((line) => line.startsWith("event:"))
          ?.slice(6)
          .trim();
        const data = frame
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");
        if (data) onEvent(type || "message", JSON.parse(data));
        if (type === "done") complete = true;
      }
      if (done) break;
    }
    if (!complete)
      throw new Error(
        "The connection ended before the response finished. Your saved chat will reload.",
      );
  } finally {
    reader.releaseLock();
  }
}
