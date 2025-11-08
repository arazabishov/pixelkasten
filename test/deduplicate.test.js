import { test, describe, before, after } from "node:test";
import { strictEqual, ok } from "node:assert";
import { deduplicate } from "../src/deduplicate.js";
import { consola } from "consola";

describe("deduplicate", () => {
  before(() => {
    consola.mockTypes(() => () => {
      /* noop */
    });
  });

  test("should handle empty workspace", () => {
    const workspace = {
      media: new Map(),
      albums: new Map(),
    };

    const result = deduplicate(workspace, { verbose: false });

    strictEqual(result.library.size, 0);
    strictEqual(result.duplicates.size, 0);
  });

  test("should process single media file without album", () => {
    const workspace = {
      media: new Map([
        [
          "/test/dir/photo1.jpg",
          {
            media: {
              entry: { path: "/test/dir", name: "photo1.jpg" },
              sha256: "abc123",
            },
          },
        ],
      ]),
      albums: new Map(),
    };

    const result = deduplicate(workspace, { verbose: false });

    strictEqual(result.library.size, 1);
    strictEqual(result.duplicates.size, 1);
    ok(result.library.has("/test/dir/photo1.jpg"));
    ok(result.duplicates.has("abc123"));
    strictEqual(result.duplicates.get("abc123").length, 0);
  });

  test("should detect duplicate files with same sha256", () => {
    const workspace = {
      media: new Map([
        [
          "/test/dir/photo1.jpg",
          {
            media: {
              entry: { path: "/test/dir", name: "photo1.jpg" },
              sha256: "abc123",
            },
          },
        ],
        [
          "/test/dir/photo1_copy.jpg",
          {
            media: {
              entry: { path: "/test/dir", name: "photo1_copy.jpg" },
              sha256: "abc123",
            },
          },
        ],
      ]),
      albums: new Map(),
    };

    const result = deduplicate(workspace, { verbose: false });

    strictEqual(result.library.size, 1);
    strictEqual(result.duplicates.size, 1);
    ok(result.library.has("/test/dir/photo1.jpg"));
    ok(result.duplicates.has("abc123"));
    strictEqual(result.duplicates.get("abc123").length, 1);
    strictEqual(result.duplicates.get("abc123")[0].media.entry.name, "photo1_copy.jpg");
  });

  test("should detect multiple duplicates of same file", () => {
    const workspace = {
      media: new Map([
        [
          "/test/dir/photo1.jpg",
          {
            media: {
              entry: { path: "/test/dir", name: "photo1.jpg" },
              sha256: "abc123",
            },
          },
        ],
        [
          "/test/dir/photo1_copy1.jpg",
          {
            media: {
              entry: { path: "/test/dir", name: "photo1_copy1.jpg" },
              sha256: "abc123",
            },
          },
        ],
        [
          "/test/dir/photo1_copy2.jpg",
          {
            media: {
              entry: { path: "/test/dir", name: "photo1_copy2.jpg" },
              sha256: "abc123",
            },
          },
        ],
      ]),
      albums: new Map(),
    };

    const result = deduplicate(workspace, { verbose: false });

    strictEqual(result.library.size, 1);
    strictEqual(result.duplicates.size, 1);
    strictEqual(result.duplicates.get("abc123").length, 2);
  });

  test("should handle multiple unique files", () => {
    const workspace = {
      media: new Map([
        [
          "/test/dir/photo1.jpg",
          {
            media: {
              entry: { path: "/test/dir", name: "photo1.jpg" },
              sha256: "abc123",
            },
          },
        ],
        [
          "/test/dir/photo2.jpg",
          {
            media: {
              entry: { path: "/test/dir", name: "photo2.jpg" },
              sha256: "def456",
            },
          },
        ],
        [
          "/test/dir/photo3.jpg",
          {
            media: {
              entry: { path: "/test/dir", name: "photo3.jpg" },
              sha256: "ghi789",
            },
          },
        ],
      ]),
      albums: new Map(),
    };

    const result = deduplicate(workspace, { verbose: false });

    strictEqual(result.library.size, 3);
    strictEqual(result.duplicates.size, 3);
    ok(result.library.has("/test/dir/photo1.jpg"));
    ok(result.library.has("/test/dir/photo2.jpg"));
    ok(result.library.has("/test/dir/photo3.jpg"));
  });

  test("should create album directory in library", () => {
    const workspace = {
      media: new Map(),
      albums: new Map([
        ["/test/albums/vacation", { path: "/test/albums/vacation", name: "metadata.json" }],
      ]),
    };

    const result = deduplicate(workspace, { verbose: false });

    strictEqual(result.library.size, 1);
    ok(result.library.has("/test/albums/vacation"));
    const album = result.library.get("/test/albums/vacation");
    ok(album.metadata);
    ok(Array.isArray(album.items));
    strictEqual(album.items.length, 0);
  });

  test("should process media files in album directory", () => {
    const workspace = {
      media: new Map([
        [
          "/test/albums/vacation/photo1.jpg",
          {
            media: {
              entry: { path: "/test/albums/vacation", name: "photo1.jpg" },
              sha256: "abc123",
            },
          },
        ],
        [
          "/test/albums/vacation/photo2.jpg",
          {
            media: {
              entry: { path: "/test/albums/vacation", name: "photo2.jpg" },
              sha256: "def456",
            },
          },
        ],
      ]),
      albums: new Map([
        ["/test/albums/vacation", { path: "/test/albums/vacation", name: "metadata.json" }],
      ]),
    };

    const result = deduplicate(workspace, { verbose: false });

    strictEqual(result.library.size, 1);
    ok(result.library.has("/test/albums/vacation"));
    const album = result.library.get("/test/albums/vacation");
    strictEqual(album.items.length, 2);
    strictEqual(album.items[0].media.entry.name, "photo1.jpg");
    strictEqual(album.items[1].media.entry.name, "photo2.jpg");
  });

  test("should detect duplicates within album", () => {
    const workspace = {
      media: new Map([
        [
          "/test/albums/vacation/photo1.jpg",
          {
            media: {
              entry: { path: "/test/albums/vacation", name: "photo1.jpg" },
              sha256: "abc123",
            },
          },
        ],
        [
          "/test/albums/vacation/photo1_copy.jpg",
          {
            media: {
              entry: { path: "/test/albums/vacation", name: "photo1_copy.jpg" },
              sha256: "abc123",
            },
          },
        ],
      ]),
      albums: new Map([
        ["/test/albums/vacation", { path: "/test/albums/vacation", name: "metadata.json" }],
      ]),
    };

    const result = deduplicate(workspace, { verbose: false });

    strictEqual(result.library.size, 1);
    const album = result.library.get("/test/albums/vacation");
    strictEqual(album.items.length, 1);
    strictEqual(album.items[0].media.entry.name, "photo1.jpg");
    ok(result.duplicates.has("abc123"));
    strictEqual(result.duplicates.get("abc123").length, 1);
    strictEqual(result.duplicates.get("abc123")[0].media.entry.name, "photo1_copy.jpg");
  });

  test("should handle mixed album and non-album files", () => {
    const workspace = {
      media: new Map([
        [
          "/test/albums/vacation/photo1.jpg",
          {
            media: {
              entry: { path: "/test/albums/vacation", name: "photo1.jpg" },
              sha256: "abc123",
            },
          },
        ],
        [
          "/test/dir/photo2.jpg",
          {
            media: {
              entry: { path: "/test/dir", name: "photo2.jpg" },
              sha256: "def456",
            },
          },
        ],
      ]),
      albums: new Map([
        ["/test/albums/vacation", { path: "/test/albums/vacation", name: "metadata.json" }],
      ]),
    };

    const result = deduplicate(workspace, { verbose: false });

    strictEqual(result.library.size, 2);
    ok(result.library.has("/test/albums/vacation"));
    ok(result.library.has("/test/dir/photo2.jpg"));
    const album = result.library.get("/test/albums/vacation");
    strictEqual(album.items.length, 1);
  });

  test("should detect duplicates across album and non-album files", () => {
    const workspace = {
      media: new Map([
        [
          "/test/albums/vacation/photo1.jpg",
          {
            media: {
              entry: { path: "/test/albums/vacation", name: "photo1.jpg" },
              sha256: "abc123",
            },
          },
        ],
        [
          "/test/dir/photo1_copy.jpg",
          {
            media: {
              entry: { path: "/test/dir", name: "photo1_copy.jpg" },
              sha256: "abc123",
            },
          },
        ],
      ]),
      albums: new Map([
        ["/test/albums/vacation", { path: "/test/albums/vacation", name: "metadata.json" }],
      ]),
    };

    const result = deduplicate(workspace, { verbose: false });

    strictEqual(result.library.size, 1);
    const album = result.library.get("/test/albums/vacation");
    strictEqual(album.items.length, 1);
    strictEqual(album.items[0].media.entry.name, "photo1.jpg");
    ok(result.duplicates.has("abc123"));
    strictEqual(result.duplicates.get("abc123").length, 1);
    strictEqual(result.duplicates.get("abc123")[0].media.entry.name, "photo1_copy.jpg");
  });

  test("should handle multiple albums", () => {
    const workspace = {
      media: new Map([
        [
          "/test/albums/vacation/photo1.jpg",
          {
            media: {
              entry: { path: "/test/albums/vacation", name: "photo1.jpg" },
              sha256: "abc123",
            },
          },
        ],
        [
          "/test/albums/birthday/photo2.jpg",
          {
            media: {
              entry: { path: "/test/albums/birthday", name: "photo2.jpg" },
              sha256: "def456",
            },
          },
        ],
      ]),
      albums: new Map([
        ["/test/albums/vacation", { path: "/test/albums/vacation", name: "metadata.json" }],
        ["/test/albums/birthday", { path: "/test/albums/birthday", name: "metadata.json" }],
      ]),
    };

    const result = deduplicate(workspace, { verbose: false });

    strictEqual(result.library.size, 2);
    ok(result.library.has("/test/albums/vacation"));
    ok(result.library.has("/test/albums/birthday"));
    strictEqual(result.library.get("/test/albums/vacation").items.length, 1);
    strictEqual(result.library.get("/test/albums/birthday").items.length, 1);
  });

  test("should preserve metadata entries with media files", () => {
    const workspace = {
      media: new Map([
        [
          "/test/dir/photo1.jpg",
          {
            media: {
              entry: { path: "/test/dir", name: "photo1.jpg" },
              sha256: "abc123",
            },
            metadata: { path: "/test/dir", name: "photo1.jpg.json" },
          },
        ],
      ]),
      albums: new Map(),
    };

    const result = deduplicate(workspace, { verbose: false });

    const entry = result.library.get("/test/dir/photo1.jpg");
    ok(entry.media);
    ok(entry.metadata);
    strictEqual(entry.metadata.name, "photo1.jpg.json");
  });

  test("should handle complex scenario with multiple duplicates and albums", () => {
    const workspace = {
      media: new Map([
        [
          "/albums/vacation/photo1.jpg",
          {
            media: {
              entry: { path: "/albums/vacation", name: "photo1.jpg" },
              sha256: "sha1",
            },
          },
        ],
        [
          "/albums/vacation/photo2.jpg",
          {
            media: {
              entry: { path: "/albums/vacation", name: "photo2.jpg" },
              sha256: "sha2",
            },
          },
        ],
        [
          "/albums/birthday/photo3.jpg",
          {
            media: {
              entry: { path: "/albums/birthday", name: "photo3.jpg" },
              sha256: "sha3",
            },
          },
        ],
        [
          "/standalone/photo4.jpg",
          {
            media: {
              entry: { path: "/standalone", name: "photo4.jpg" },
              sha256: "sha4",
            },
          },
        ],
        [
          "/standalone/photo1_dup.jpg",
          {
            media: {
              entry: { path: "/standalone", name: "photo1_dup.jpg" },
              sha256: "sha1",
            },
          },
        ],
        [
          "/standalone/photo4_dup.jpg",
          {
            media: {
              entry: { path: "/standalone", name: "photo4_dup.jpg" },
              sha256: "sha4",
            },
          },
        ],
      ]),
      albums: new Map([
        ["/albums/vacation", { path: "/albums/vacation", name: "metadata.json" }],
        ["/albums/birthday", { path: "/albums/birthday", name: "metadata.json" }],
      ]),
    };

    const result = deduplicate(workspace, { verbose: false });
    strictEqual(result.library.size, 3);

    const vacation = result.library.get("/albums/vacation");
    strictEqual(vacation.items.length, 2);

    const birthday = result.library.get("/albums/birthday");
    strictEqual(birthday.items.length, 1);

    ok(result.library.has("/standalone/photo4.jpg"));

    strictEqual(result.duplicates.size, 4);
    strictEqual(result.duplicates.get("sha1").length, 1);
    strictEqual(result.duplicates.get("sha4").length, 1);
  });
});
