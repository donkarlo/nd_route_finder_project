package com.ndroutefinder.garmin;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;

import java.io.File;
import java.io.FileNotFoundException;

public final class GpxProvider extends ContentProvider {
    public static final String AUTHORITY = "com.ndroutefinder.garmin.files";
    private static final String SHARE_DIR = "garmin_share";

    @Override
    public boolean onCreate() {
        return true;
    }

    private File resolve(Uri uri) throws FileNotFoundException {
        if (getContext() == null) {
            throw new FileNotFoundException("No context");
        }
        String name = uri.getLastPathSegment();
        if (name == null || name.trim().isEmpty() || name.contains("/") || name.contains("\\") || name.contains("..")) {
            throw new FileNotFoundException("Invalid file name");
        }

        File dir = new File(getContext().getCacheDir(), SHARE_DIR);
        File file = new File(dir, name);

        try {
            String dirPath = dir.getCanonicalPath() + File.separator;
            String filePath = file.getCanonicalPath();
            if (!filePath.startsWith(dirPath)) {
                throw new FileNotFoundException("Path outside share directory");
            }
        } catch (Exception e) {
            throw new FileNotFoundException("Invalid path");
        }

        if (!file.isFile()) {
            throw new FileNotFoundException(name);
        }
        return file;
    }

    @Override
    public String getType(Uri uri) {
        return "application/gpx+xml";
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (!"r".equals(mode)) {
            throw new FileNotFoundException("Read only");
        }
        return ParcelFileDescriptor.open(resolve(uri), ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override
    public Cursor query(
            Uri uri,
            String[] projection,
            String selection,
            String[] selectionArgs,
            String sortOrder
    ) {
        try {
            File file = resolve(uri);
            MatrixCursor cursor = new MatrixCursor(new String[] {
                    OpenableColumns.DISPLAY_NAME,
                    OpenableColumns.SIZE
            });
            cursor.addRow(new Object[] { file.getName(), file.length() });
            return cursor;
        } catch (FileNotFoundException e) {
            return null;
        }
    }

    @Override
    public Uri insert(Uri uri, ContentValues values) {
        throw new UnsupportedOperationException("Read only");
    }

    @Override
    public int delete(Uri uri, String selection, String[] selectionArgs) {
        throw new UnsupportedOperationException("Read only");
    }

    @Override
    public int update(Uri uri, ContentValues values, String selection, String[] selectionArgs) {
        throw new UnsupportedOperationException("Read only");
    }
}
