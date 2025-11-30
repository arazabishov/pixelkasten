import { test, describe } from "node:test";
import { strictEqual } from "node:assert";
import { dedupeResolve } from "../../src/stages/dedupe.js";

describe("dedupeResolve", () => {
  describe("unique files (no duplicates)", () => {
    test("should mark all unique files as keep", () => {
      const manifest = [
        {
          mediaPath: "/tmp/photo1.jpg",
          source: { type: "loose" },
          dedupe: { hash: "hash1", action: "pending" },
        },
        {
          mediaPath: "/tmp/photo2.jpg",
          source: { type: "loose" },
          dedupe: { hash: "hash2", action: "pending" },
        },
        {
          mediaPath: "/tmp/album1/photo3.jpg",
          source: { type: "album", name: "Vacation" },
          dedupe: { hash: "hash3", action: "pending" },
        },
      ];

      dedupeResolve(manifest, { prefer: "album" });

      // Verify all unique files are marked as keep
      strictEqual(manifest[0].dedupe.action, "keep");

      strictEqual(manifest[1].dedupe.action, "keep");

      strictEqual(manifest[2].dedupe.action, "keep");
    });

    test("should mark unique file as keep regardless of preference", () => {
      const manifestAlbum = [
        {
          mediaPath: "/tmp/album1/photo1.jpg",
          source: { type: "album", name: "Vacation" },
          dedupe: { hash: "hash1", action: "pending" },
        },
      ];

      const manifestLoose = [
        {
          mediaPath: "/tmp/photo1.jpg",
          source: { type: "loose" },
          dedupe: { hash: "hash1", action: "pending" },
        },
      ];

      dedupeResolve(manifestAlbum, { prefer: "album" });
      // Verify album file is kept with album preference
      strictEqual(manifestAlbum[0].dedupe.action, "keep");

      dedupeResolve(manifestAlbum, { prefer: "loose" });
      // Verify album file is kept with loose preference
      strictEqual(manifestAlbum[0].dedupe.action, "keep");

      dedupeResolve(manifestLoose, { prefer: "album" });
      // Verify loose file is kept with album preference
      strictEqual(manifestLoose[0].dedupe.action, "keep");

      dedupeResolve(manifestLoose, { prefer: "loose" });
      // Verify loose file is kept with loose preference
      strictEqual(manifestLoose[0].dedupe.action, "keep");
    });
  });

  describe("prefer album", () => {
    test("should keep album and delete loose when preferring album", () => {
      const manifest = [
        {
          mediaPath: "/tmp/album1/photo1.jpg",
          source: { type: "album", name: "Vacation" },
          dedupe: { hash: "hash1", action: "pending" },
        },
        {
          mediaPath: "/tmp/photo1.jpg",
          source: { type: "loose" },
          dedupe: { hash: "hash1", action: "pending" },
        },
      ];

      dedupeResolve(manifest, { prefer: "album" });

      strictEqual(manifest[0].dedupe.action, "keep");
      strictEqual(manifest[1].dedupe.action, "delete");
    });

    test("should keep multiple albums and delete loose when preferring album", () => {
      const manifest = [
        {
          mediaPath: "/tmp/album1/photo1.jpg",
          source: { type: "album", name: "Vacation" },
          dedupe: { hash: "hash1", action: "pending" },
        },
        {
          mediaPath: "/tmp/album2/photo1.jpg",
          source: { type: "album", name: "Birthday" },
          dedupe: { hash: "hash1", action: "pending" },
        },
        {
          mediaPath: "/tmp/photo1.jpg",
          source: { type: "loose" },
          dedupe: { hash: "hash1", action: "pending" },
        },
      ];

      dedupeResolve(manifest, { prefer: "album" });

      // Verify both albums are kept
      strictEqual(manifest[0].dedupe.action, "keep");

      strictEqual(manifest[1].dedupe.action, "keep");

      // Verify loose is deleted
      strictEqual(manifest[2].dedupe.action, "delete");
    });

    test("should handle multiple duplicates with mixed sources", () => {
      const manifest = [
        {
          mediaPath: "/tmp/album1/photo1.jpg",
          source: { type: "album", name: "Vacation" },
          dedupe: { hash: "hash1", action: "pending" },
        },
        {
          mediaPath: "/tmp/photo1.jpg",
          source: { type: "loose" },
          dedupe: { hash: "hash1", action: "pending" },
        },
        {
          mediaPath: "/tmp/photo1_copy.jpg",
          source: { type: "loose" },
          dedupe: { hash: "hash1", action: "pending" },
        },
      ];

      dedupeResolve(manifest, { prefer: "album" });

      // Verify album is kept
      strictEqual(manifest[0].dedupe.action, "keep");

      // Verify all loose files are deleted
      strictEqual(manifest[1].dedupe.action, "delete");

      strictEqual(manifest[2].dedupe.action, "delete");
    });
  });

  describe("prefer loose", () => {
    test("should keep loose and delete album when preferring loose", () => {
      const manifest = [
        {
          mediaPath: "/tmp/album1/photo1.jpg",
          source: { type: "album", name: "Vacation" },
          dedupe: { hash: "hash1", action: "pending" },
        },
        {
          mediaPath: "/tmp/photo1.jpg",
          source: { type: "loose" },
          dedupe: { hash: "hash1", action: "pending" },
        },
      ];

      dedupeResolve(manifest, { prefer: "loose" });

      strictEqual(manifest[0].dedupe.action, "delete");
      strictEqual(manifest[1].dedupe.action, "keep");
    });

    test("should keep multiple loose and delete album when preferring loose", () => {
      const manifest = [
        {
          mediaPath: "/tmp/album1/photo1.jpg",
          source: { type: "album", name: "Vacation" },
          dedupe: { hash: "hash1", action: "pending" },
        },
        {
          mediaPath: "/tmp/photo1.jpg",
          source: { type: "loose" },
          dedupe: { hash: "hash1", action: "pending" },
        },
        {
          mediaPath: "/tmp/photo1_copy.jpg",
          source: { type: "loose" },
          dedupe: { hash: "hash1", action: "pending" },
        },
      ];

      dedupeResolve(manifest, { prefer: "loose" });

      // Verify album is deleted
      strictEqual(manifest[0].dedupe.action, "delete");

      // Verify all loose files are kept
      strictEqual(manifest[1].dedupe.action, "keep");

      strictEqual(manifest[2].dedupe.action, "keep");
    });

    test("should delete all albums when multiple albums and loose prefer loose", () => {
      const manifest = [
        {
          mediaPath: "/tmp/album1/photo1.jpg",
          source: { type: "album", name: "Vacation" },
          dedupe: { hash: "hash1", action: "pending" },
        },
        {
          mediaPath: "/tmp/album2/photo1.jpg",
          source: { type: "album", name: "Birthday" },
          dedupe: { hash: "hash1", action: "pending" },
        },
        {
          mediaPath: "/tmp/photo1.jpg",
          source: { type: "loose" },
          dedupe: { hash: "hash1", action: "pending" },
        },
      ];

      dedupeResolve(manifest, { prefer: "loose" });

      // Verify all albums are deleted
      strictEqual(manifest[0].dedupe.action, "delete");

      strictEqual(manifest[1].dedupe.action, "delete");

      // Verify loose is kept
      strictEqual(manifest[2].dedupe.action, "keep");
    });
  });

  describe("same-type duplicates (preference irrelevant)", () => {
    test("should keep all duplicates when all are albums", () => {
      const manifest = [
        {
          mediaPath: "/tmp/album1/photo1.jpg",
          source: { type: "album", name: "Vacation" },
          dedupe: { hash: "hash1", action: "pending" },
        },
        {
          mediaPath: "/tmp/album2/photo1.jpg",
          source: { type: "album", name: "Birthday" },
          dedupe: { hash: "hash1", action: "pending" },
        },
      ];

      dedupeResolve(manifest, { prefer: "album" });

      strictEqual(manifest[0].dedupe.action, "keep");
      strictEqual(manifest[1].dedupe.action, "keep");
    });

    test("should keep all duplicates when all are loose", () => {
      const manifest = [
        {
          mediaPath: "/tmp/photo1.jpg",
          source: { type: "loose" },
          dedupe: { hash: "hash1", action: "pending" },
        },
        {
          mediaPath: "/tmp/photo1_copy.jpg",
          source: { type: "loose" },
          dedupe: { hash: "hash1", action: "pending" },
        },
      ];

      dedupeResolve(manifest, { prefer: "album" });

      strictEqual(manifest[0].dedupe.action, "keep");
      strictEqual(manifest[1].dedupe.action, "keep");
    });
  });

  describe("multiple hash groups", () => {
    test("should handle multiple independent duplicate groups", () => {
      const manifest = [
        {
          mediaPath: "/tmp/album1/photo1.jpg",
          source: { type: "album", name: "Vacation" },
          dedupe: { hash: "hash1", action: "pending" },
        },
        {
          mediaPath: "/tmp/photo1.jpg",
          source: { type: "loose" },
          dedupe: { hash: "hash1", action: "pending" },
        },
        {
          mediaPath: "/tmp/album2/photo2.jpg",
          source: { type: "album", name: "Birthday" },
          dedupe: { hash: "hash2", action: "pending" },
        },
        {
          mediaPath: "/tmp/photo2.jpg",
          source: { type: "loose" },
          dedupe: { hash: "hash2", action: "pending" },
        },
        {
          mediaPath: "/tmp/photo3.jpg",
          source: { type: "loose" },
          dedupe: { hash: "hash3", action: "pending" },
        },
      ];

      dedupeResolve(manifest, { prefer: "album" });

      // Verify first duplicate group (prefer album)
      strictEqual(manifest[0].dedupe.action, "keep");

      strictEqual(manifest[1].dedupe.action, "delete");

      // Verify second duplicate group (prefer album)
      strictEqual(manifest[2].dedupe.action, "keep");

      strictEqual(manifest[3].dedupe.action, "delete");

      // Verify unique file is kept
      strictEqual(manifest[4].dedupe.action, "keep");
    });
  });

  describe("edge cases", () => {
    test("should handle empty manifest", () => {
      const manifest = [];

      dedupeResolve(manifest, { prefer: "album" });

      // Verify empty manifest remains empty
      strictEqual(manifest.length, 0);
    });

    test("should handle single file", () => {
      const manifest = [
        {
          mediaPath: "/tmp/photo1.jpg",
          source: { type: "loose" },
          dedupe: { hash: "hash1", action: "pending" },
        },
      ];

      dedupeResolve(manifest, { prefer: "album" });

      strictEqual(manifest[0].dedupe.action, "keep");
    });
  });
});
