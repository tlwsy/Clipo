package app.clipo.android

import android.app.Application
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.PredictiveBackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ExitToApp
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LargeTopAppBar
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationRail
import androidx.compose.material3.NavigationRailItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.VerticalDivider
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import app.clipo.shared.MobileModel
import app.clipo.shared.MobileState
import app.clipo.shared.Screen
import app.clipo.shared.createAndroidClient
import kotlinx.coroutines.CancellationException

class ClipoViewModel(
    application: Application,
) : AndroidViewModel(application) {
    val model = MobileModel(createAndroidClient(application))

    override fun onCleared() {
        model.close()
    }
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val context = LocalContext.current
            val dark = isSystemInDarkTheme()
            val colors =
                if (Build.VERSION.SDK_INT >= 31) {
                    if (dark) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
                } else {
                    if (dark) darkColorScheme() else lightColorScheme()
                }
            MaterialTheme(colorScheme = colors) { ClipoApp(viewModel<ClipoViewModel>().model) }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ClipoApp(model: MobileModel) {
    val state by model.state.collectAsStateWithLifecycle()
    var confirmLogout by remember { mutableStateOf(false) }
    var settings by rememberSaveable { mutableStateOf(false) }
    var backProgress by remember { mutableFloatStateOf(0f) }
    PredictiveBackHandler(state.selectedId != null && !settings && state.readingDraft == null) { events ->
        try {
            events.collect { backProgress = it.progress }
            model.closeNote()
        } catch (_: CancellationException) {
            // A cancelled gesture keeps the reader and its scroll position.
        } finally {
            backProgress = 0f
        }
    }
    val scrollBehavior = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val wide = maxWidth >= 840.dp
        Scaffold(
            modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
            bottomBar = {
                if (!wide && state.screen == Screen.NOTES) {
                    NavigationBar {
                        NavigationBarItem(
                            selected = !settings,
                            onClick = { settings = false },
                            icon = { Icon(Icons.AutoMirrored.Filled.List, null) },
                            label = { Text(stringResource(R.string.notes)) },
                        )
                        NavigationBarItem(
                            selected = settings,
                            onClick = { settings = true },
                            icon = { Icon(Icons.Default.Settings, null) },
                            label = { Text(stringResource(R.string.settings)) },
                        )
                    }
                }
            },
            topBar = {
                LargeTopAppBar(
                    scrollBehavior = scrollBehavior,
                    title = {
                        Text(
                            if (state.screen ==
                                Screen.NOTES
                            ) {
                                stringResource(if (settings) R.string.settings else R.string.notes)
                            } else {
                                "Clipo"
                            },
                        )
                    },
                    navigationIcon = {
                        if (state.selectedId !=
                            null
                        ) {
                            IconButton(
                                onClick = model::closeNote,
                            ) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back)) }
                        }
                    },
                    actions = {
                        if (state.detail != null && !settings && state.screen == Screen.NOTES) {
                            IconButton(onClick = { model.beginReading(true) }) {
                                Icon(Icons.Default.Settings, stringResource(R.string.reading_style))
                            }
                        }
                        if (state.account != null) {
                            IconButton(onClick = {
                                confirmLogout = true
                            }) { Icon(Icons.AutoMirrored.Filled.ExitToApp, stringResource(R.string.logout)) }
                        }
                    },
                )
            },
        ) { padding ->
            Column(Modifier.fillMaxSize().padding(padding)) {
                if (state.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
                state.failure?.let {
                    Text(it.message, Modifier.padding(16.dp), color = MaterialTheme.colorScheme.error)
                    if (state.screen ==
                        Screen.NOTES
                    ) {
                        Text(stringResource(R.string.cached_hint), Modifier.padding(horizontal = 16.dp))
                    }
                }
                when (state.screen) {
                    Screen.SERVER, Screen.LOGIN -> LoginForm(state, model)
                    Screen.NOTES ->
                        Row(Modifier.fillMaxSize()) {
                            if (wide) {
                                NavigationRail {
                                    NavigationRailItem(
                                        selected = !settings,
                                        onClick = { settings = false },
                                        icon = { Icon(Icons.AutoMirrored.Filled.List, null) },
                                        label = { Text(stringResource(R.string.notes)) },
                                    )
                                    NavigationRailItem(
                                        selected = settings,
                                        onClick = { settings = true },
                                        icon = { Icon(Icons.Default.Settings, null) },
                                        label = { Text(stringResource(R.string.settings)) },
                                    )
                                }
                            }
                            if (settings) {
                                Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                                    Text(
                                        state.account?.username.orEmpty(),
                                        style = MaterialTheme.typography.headlineSmall,
                                    )
                                    Text(state.server)
                                    Text(stringResource(R.string.version, state.serverVersion))
                                    Button(
                                        onClick = { model.beginReading(false) },
                                    ) { Text(stringResource(R.string.global_reading)) }
                                }
                            } else if (wide) {
                                Box(Modifier.width(300.dp).fillMaxHeight()) { Notes(state, model) }
                                VerticalDivider()
                                Box(Modifier.weight(1f).fillMaxHeight()) {
                                    if (state.selectedId ==
                                        null
                                    ) {
                                        Text(stringResource(R.string.select_note), Modifier.align(Alignment.Center))
                                    } else {
                                        key(state.selectedId) { Reader(state, model) }
                                    }
                                }
                            } else {
                                Box(Modifier.fillMaxSize()) {
                                    if (state.selectedId == null || backProgress > 0f) Notes(state, model)
                                    if (state.selectedId != null) {
                                        Box(
                                            Modifier.fillMaxSize().graphicsLayer {
                                                translationX = size.width * backProgress
                                                scaleX = 1f - backProgress * 0.05f
                                                scaleY = scaleX
                                            },
                                        ) { key(state.selectedId) { Reader(state, model) } }
                                    }
                                }
                            }
                        }
                }
            }
        }
    }
    if (state.readingDraft != null) ReadingDialog(state, model)
    if (confirmLogout) {
        AlertDialog(
            onDismissRequest = { confirmLogout = false },
            title = { Text(stringResource(R.string.logout_title)) },
            text = { Text(stringResource(R.string.logout_message)) },
            confirmButton = {
                TextButton(onClick = {
                    confirmLogout = false
                    model.logout()
                }) { Text(stringResource(R.string.logout)) }
            },
            dismissButton = {
                TextButton(onClick = { confirmLogout = false }) { Text(stringResource(R.string.cancel)) }
            },
        )
    }
}

@Composable
private fun LoginForm(
    state: MobileState,
    model: MobileModel,
) {
    var server by rememberSaveable(state.server) { mutableStateOf(state.server) }
    var username by rememberSaveable { mutableStateOf("") }
    // Passwords never enter saved instance state or the shared model.
    var password by remember { mutableStateOf("") }
    LazyColumn(
        Modifier.fillMaxWidth().widthIn(max = 600.dp),
        contentPadding = PaddingValues(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item { Text(stringResource(R.string.server_title), style = MaterialTheme.typography.headlineMedium) }
        if (state.screen == Screen.SERVER) {
            item { Text(stringResource(R.string.server_hint)) }
            item {
                OutlinedTextField(server, {
                    server = it
                }, Modifier.fillMaxWidth(), label = {
                    Text(stringResource(R.string.server))
                }, singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
            }
            item {
                Button(onClick = {
                    model.inspectServer(server)
                }, enabled = !state.busy && server.isNotBlank()) { Text(stringResource(R.string.continue_action)) }
            }
        } else {
            item {
                Text(state.server)
                Text(stringResource(R.string.version, state.serverVersion))
            }
            if (state.server.startsWith("http:")) item { Text(stringResource(R.string.http_hint)) }
            item {
                OutlinedTextField(username, {
                    username = it
                }, Modifier.fillMaxWidth(), label = { Text(stringResource(R.string.username)) }, singleLine = true)
            }
            item {
                OutlinedTextField(
                    password,
                    {
                        password = it
                    },
                    Modifier.fillMaxWidth(),
                    label = {
                        Text(stringResource(R.string.password))
                    },
                    singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions =
                        KeyboardOptions(
                            keyboardType = KeyboardType.Password,
                        ),
                )
            }
            item {
                Button(
                    onClick = {
                        model.login(username, password)
                        password = ""
                    },
                    enabled =
                        !state.busy && username.isNotBlank() && password.isNotEmpty(),
                ) { Text(stringResource(R.string.login)) }
            }
            if (state.account ==
                null
            ) {
                item { TextButton(onClick = model::editServer) { Text(stringResource(R.string.change_server)) } }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun Notes(
    state: MobileState,
    model: MobileModel,
) {
    PullToRefreshBox(isRefreshing = state.busy, onRefresh = { model.refreshNotes() }) {
        LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Button(
                    onClick = { model.refreshNotes() },
                    enabled = !state.busy,
                ) { Text(stringResource(R.string.refresh)) }
            }
            if (state.notes.isEmpty()) {
                item {
                    Text(
                        stringResource(if (state.busy) R.string.loading else R.string.empty),
                    )
                }
            }
            items(state.notes, key = { it.id }) { note ->
                Card(Modifier.fillMaxWidth().clickable { model.openNote(note.id) }) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(note.title, style = MaterialTheme.typography.titleLarge)
                        Text(
                            listOfNotNull(note.siteName ?: note.platform, note.author).joinToString(" · "),
                            style = MaterialTheme.typography.labelMedium,
                        )
                        Text(note.summaryExcerpt, maxLines = 3, overflow = TextOverflow.Ellipsis)
                        Row { Text(note.createdAt.take(10), style = MaterialTheme.typography.labelSmall) }
                    }
                }
            }
            if (state.hasMore && state.notes.isNotEmpty()) {
                item {
                    TextButton(onClick = {
                        model.refreshNotes(true)
                    }, enabled = !state.busy) { Text(stringResource(R.string.load_more)) }
                }
            }
        }
    }
}
