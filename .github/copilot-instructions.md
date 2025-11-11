# **Guiding Principles: PixelKasten**

This document outlines the high-level requirements for a script that processes media files and sidecar .json files from a Google Photos Takeout.

## **1\. Core Objective**

The primary goal is to write metadata (timestamps, geo-data) from .json sidecar files into their corresponding media files (images, videos). This can be extended to other metadata tags in the future.

- **Implementation:** The solution will be a **Node.js script**.
- **Core Tool:** The script will orchestrate a metadata-writing tool (like exiftool) to apply changes, using Node.js's child_process to execute commands.

## **2\. Guiding Principles (Constraints)**

The script **MUST** adhere to the following rules:

### **Principle 1: Do Not Overwrite Existing Data**

If a media file already contains the relevant native metadata, it MUST NOT be updated.

- **Timestamp Check:** Before writing, the script must check for the existence of relevant _native_ timestamp tags for that file format.
- **Geo-Data Check:** Before writing, the script must check for the existence of relevant _native_ geo-data tags for that file format.
- **Implementation:** The script should first read and parse existing metadata from the media file before deciding whether to write new data.

### **Principle 2: Validate Input Data**

Invalid data from the .json sidecar must be ignored.

- **Geo-Data Check:** If geoData.latitude or geoData.longitude are 0, 0.0, null, or undefined, the script MUST NOT write _any_ geo-data for that file.

### **Principle 3: Use Native Tags & Correct Formatting**

Metadata MUST be written to the correct native tags for each file format, and the value MUST be formatted to that tag's standard.

- **JSON Source Data:**
  - photoTakenTime.timestamp: UTC-based Unix epoch string.
  - geoData: Signed decimal latitude, longitude, and altitude.
- **Format-Specific Logic:** The script must contain a ruleset to map file extensions (e..g., .jpg, .png, .mov, .mp4, .gif) to their correct native tags and required value formats (e.g., EXIF for JPEG, QuickTime tags for MOV). This logic must handle the correct formatting of timestamps (with or without timezones) and geo-data as required by the native standard.

### **Principle 4: Be Strict on Unknown Formats**

The script must _only_ process file formats for which it has explicit rules.

- **Handling:** If an unknown file format (e.g., .mkv, .avi) is encountered, the script MUST skip it.
- **Reporting:** At the end of its run, the script should produce a summary that includes a list of all skipped files with unknown extensions. This is preferable to writing non-standard "fallback" tags.

## **3\. Development & Operational Principles**

### **Principle 5: Prioritize Simplicity**

The project should favor simplicity over complexity. The number of third-party dependencies should be kept to a minimum. Any dependency that is added must be scrutinized and justified.

### **Principle 6: Ensure Testability**

The project must have good automated test coverage. Tests should be written using the native Node.js testing framework.

### **Principle 7: Maintain Transparency**

The project should keep a good level of transparency and report on its execution. This includes logging the outcomes of different phases and providing a final summary.

- **Reporting:** The script must report on file statuses, such as how many files were successfully matched with metadata, how many were skipped (and why, e.g., "existing data" or "unknown format"), and how many media files or .json files did not have a matching pair.
