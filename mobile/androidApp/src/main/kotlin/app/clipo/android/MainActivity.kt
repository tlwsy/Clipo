package app.clipo.android

import android.app.Application
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
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
    BackHandler(state.selectedId != null) { model.closeNote() }
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(if (state.screen == Screen.NOTES) stringResource(R.string.notes) else "Clipo") },
                navigationIcon = {
                    if (state.selectedId !=
                        null
                    ) {
                        TextButton(onClick = model::closeNote) { Text(stringResource(R.string.back)) }
                    }
                },
                actions = {
                    if (state.account !=
                        null
                    ) {
                        TextButton(onClick = { confirmLogout = true }) { Text(stringResource(R.string.logout)) }
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
                Screen.NOTES -> if (state.selectedId != null) Reader(state, model) else Notes(state, model)
            }
        }
    }
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

@Composable
private fun Notes(
    state: MobileState,
    model: MobileModel,
) {
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Button(onClick = { model.refreshNotes() }, enabled = !state.busy) { Text(stringResource(R.string.refresh)) }
        }
        if (state.notes.isEmpty()) item { Text(stringResource(if (state.busy) R.string.loading else R.string.empty)) }
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

@Composable
private fun Reader(
    state: MobileState,
    model: MobileModel,
) {
    val note = state.detail
    if (note == null) {
        Column(Modifier.padding(24.dp)) {
            Text(stringResource(if (state.failure == null) R.string.loading else R.string.not_cached))
            TextButton(onClick = { state.selectedId?.let(model::openNote) }) { Text(stringResource(R.string.retry)) }
        }
        return
    }
    SelectionContainer {
        LazyColumn(contentPadding = PaddingValues(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            item { Text(note.title, style = MaterialTheme.typography.headlineLarge) }
            item { Text(note.url, style = MaterialTheme.typography.labelMedium) }
            item { Text(stringResource(R.string.summary), style = MaterialTheme.typography.titleMedium) }
            item { Text(note.summaryMarkdown ?: stringResource(R.string.no_summary)) }
            items(note.keyPoints) { Text("• $it") }
            item { Text(stringResource(R.string.original), style = MaterialTheme.typography.titleMedium) }
            items(note.content.text.split("\n\n")) { Text(it, style = MaterialTheme.typography.bodyLarge) }
        }
    }
}
