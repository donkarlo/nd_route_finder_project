plugins {
    id("com.android.application")
}

android {
    namespace = "com.ndroutefinder.garmin"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.ndroutefinder.garmin"
        minSdk = 26
        targetSdk = 37
        versionCode = 2
        versionName = "0.2.0"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
