import { test, describe } from "node:test";
import assert from "node:assert";
import { normalizeMetadataName } from "../src/workspace.js";

describe("normalizeMetadataName", () => {
  test("should normalize .suppl.json metadata files", () => {
    const result = normalizeMetadataName("3D06C8D1-7637-4625-BEBE-C3D916AEF50D.jpg.suppl.json");
    assert.strictEqual(result, "3D06C8D1-7637-4625-BEBE-C3D916AEF50D.jpg");
  });

  test("should normalize .supplemental-metada.json metadata files", () => {
    const result = normalizeMetadataName("PXL_20241231_114900266.jpg.supplemental-metada.json");
    assert.strictEqual(result, "PXL_20241231_114900266.jpg");
  });

  test("should normalize .supplemental-met.json metadata files with two file extensions", () => {
    const result = normalizeMetadataName("PXL_20241231_114910784.MP.jpg.supplemental-met.json");
    assert.strictEqual(result, "PXL_20241231_114910784.MP.jpg");
  });

  test("should normalize .supplemental-metadata(N).json with duplicate markers", () => {
    const result = normalizeMetadataName("camphoto_33463914.jpg.supplemental-metadata(4).json");
    assert.strictEqual(result, "camphoto_33463914(4).jpg");
  });

  test("should normalize .supplemental-metadata(N).json with duplicate markers and two extensions", () => {
    const result = normalizeMetadataName("camphoto_33463914.MP.jpg.supplemental-metadata(4).json");
    assert.strictEqual(result, "camphoto_33463914(4).MP.jpg");
  });

  test("should normalize .(N).json with duplicate markers", () => {
    const result = normalizeMetadataName("camphoto_33463914.jpg.(4).json");
    assert.strictEqual(result, "camphoto_33463914(4).jpg");
  });

  test("should return original file name if file name has no extensions", () => {
    const result = normalizeMetadataName("camphoto_33463914");
    assert.strictEqual(result, "camphoto_33463914");
  });

  test("should return original file name if file extension is not .json", () => {
    const result = normalizeMetadataName("PXL_20241231_114900266.jpg");
    assert.strictEqual(result, "PXL_20241231_114900266.jpg");
  });

  test("should return an empty string if empty string is provided", () => {
    const result = normalizeMetadataName("");
    assert.strictEqual(result, "");
  });

  test("should return undefined if undefined is supplied", () => {
    const result = normalizeMetadataName(undefined);
    assert.strictEqual(result, undefined);
  });
});
